#!/usr/bin/env python3
"""Score format_deep3: JSON_KEY_PROG + HMAC SQL columns."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

H = json.loads((ROOT / "results" / "format_deep3_harness.json").read_text())
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
SQL = re.compile(r"SQL\[([^\]]+)\]:\s*(.+?)(?=\nSQL\[|\nANSWER_|\n#####|\Z)", re.I | re.S)


def parse_dir(d: Path) -> tuple[dict, dict]:
    seals, sqls = {}, {}
    if not d.exists():
        return seals, sqls
    for p in sorted(d.rglob("*.txt")):
        text = p.read_text()
        seals.update({m.group(1): m.group(2).strip() for m in SEAL.finditer(text)})
        tagged = list(SQL.finditer(text))
        for m in tagged:
            raw = m.group(2).strip()
            if raw.upper().startswith("UNKNOWN"):
                sqls[m.group(1)] = "UNKNOWN"
            else:
                sqls[m.group(1)] = re.sub(r"\s+", " ", raw).rstrip(";")
        if not tagged:
            m = re.search(r"(SELECT\b[\s\S]+?)(?:;|\Z)", text, re.I)
            mm = re.search(r"FD3_SQL_COL_(?:NOLEG|LEG)_\d+", text)
            cid = mm.group(0) if mm else None
            if m and cid and cid not in sqls:
                sqls[cid] = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(";")
            elif re.search(r"\bUNKNOWN\b", text, re.I) and cid and cid not in sqls:
                sqls[cid] = "UNKNOWN"
    return seals, sqls


def run_sql(db: str, sql: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    seals, sqls = parse_dir(ROOT / "results" / f"format_deep3_replies_{model}")
    by_arm: dict[str, list] = {}
    rows = []
    for c in H["cases"]:
        kind, pred = "other", "MISSING"
        if c["arm"] == "SQL_COL_ENGINE":
            pred = c.get("pred") or "MISSING"
            kind = "gold" if c.get("engine_ok") else "other"
        elif c["arm"] in ("SQL_COL_NOLEG", "SQL_COL_LEG"):
            sql = sqls.get(c["id"], "")
            if not sql:
                kind, pred = "missing", "MISSING"
            elif sql.upper() == "UNKNOWN":
                kind, pred = "unknown", "UNKNOWN"
            else:
                try:
                    got = run_sql(c["db"], sql)
                    val = got[0][0] if got and got[0][0] is not None else None
                    pred = str(val) if val is not None else "EMPTY"
                    if val == c["gold"]:
                        kind = "gold"
                    elif c.get("trap") and val == c["trap"]:
                        kind = "trap"
                    else:
                        kind = "other"
                except Exception as e:
                    kind, pred = "other", f"SQL_ERROR:{type(e).__name__}"
        else:
            pred = seals.get(c["id"], "MISSING")
            if pred == c["gold"]:
                kind = "gold"
            elif pred.upper() == "UNKNOWN":
                kind = "unknown"
            elif pred == "MISSING":
                kind = "missing"
            elif c.get("trap") and pred == c["trap"]:
                kind = "trap"
        rec = {**{k: v for k, v in c.items() if k != "gold_sql"}, "pred": pred, "kind": kind, "ok": kind == "gold"}
        if c["arm"] in ("SQL_COL_NOLEG", "SQL_COL_LEG"):
            rec["sql"] = sqls.get(c["id"], "")
        rows.append(rec)
        by_arm.setdefault(c["arm"], []).append(rec)
    summary = {}
    for arm, recs in by_arm.items():
        n = len(recs)
        k = sum(1 for r in recs if r["ok"])
        counts = {x: sum(1 for r in recs if r["kind"] == x) for x in ("gold", "trap", "unknown", "missing", "other")}
        summary[arm] = {"score": f"{k}/{n}", "wilson": wilson(k, n), "iso": recs[0].get("iso"), **counts}
    path = ROOT / "results" / f"format_deep3_{model}.json"
    path.write_text(
        json.dumps({"model": model, "n": H["n"], "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2)
    )
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
