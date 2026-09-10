#!/usr/bin/env python3
"""Score format_deep2: sealed JSON keys + executed sqlite."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

H = json.loads((ROOT / "results" / "format_deep2_harness.json").read_text())
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
            sqls[m.group(1)] = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(";")
        # Salvage a single untagged SELECT only when this file has no SQL[id] tags.
        if not tagged:
            m = re.search(r"(SELECT\b[\s\S]+?)(?:;|\Z)", text, re.I)
            cid = None
            mm = re.search(r"FD2_SQL_MODEL_\d+", text) or re.search(r"FD2_SQL_MODEL_\d+", p.name)
            if mm:
                cid = mm.group(0)
            elif p.parent.name.startswith("item_"):
                cid = f"FD2_SQL_MODEL_{p.parent.name.split('_')[-1]}"
            if m and cid and cid not in sqls:
                sqls[cid] = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(";")
    return seals, sqls


def run_sql(db: str, sql: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(sql).fetchall()
    finally:
        con.close()
    return rows


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    seals, sqls = parse_dir(ROOT / "results" / f"format_deep2_replies_{model}")
    by_arm: dict[str, list] = {}
    rows = []
    for c in H["cases"]:
        kind = "other"
        pred = "MISSING"
        if c["arm"] == "SQL_ENGINE":
            pred = c.get("pred") or "MISSING"
            kind = "gold" if c.get("engine_ok") else "other"
        elif c["arm"] == "SQL_MODEL":
            sql = sqls.get(c["id"], "")
            if not sql:
                kind, pred = "missing", "MISSING"
            else:
                pred = sql
                try:
                    got = run_sql(c["db"], sql)
                    val = got[0][0] if got and got[0][0] is not None else None
                    pred = str(val) if val is not None else "EMPTY"
                    if val == c["gold"]:
                        kind = "gold"
                    elif pred.upper() == "UNKNOWN":
                        kind = "unknown"
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
        if c["arm"] == "SQL_MODEL":
            rec["sql"] = sqls.get(c["id"], "")
        rows.append(rec)
        by_arm.setdefault(c["arm"], []).append(rec)
    summary = {}
    for arm, recs in by_arm.items():
        n = len(recs)
        k = sum(1 for r in recs if r["ok"])
        counts = {x: sum(1 for r in recs if r["kind"] == x) for x in ("gold", "trap", "unknown", "missing", "other")}
        summary[arm] = {"score": f"{k}/{n}", "wilson": wilson(k, n), "iso": recs[0].get("iso"), **counts}
    path = ROOT / "results" / f"format_deep2_{model}.json"
    path.write_text(
        json.dumps({"model": model, "n": H["n"], "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2)
    )
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
