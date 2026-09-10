#!/usr/bin/env python3
"""Spider n=32: model writes SQL; we EXECUTE in sqlite (G-Inc2 + engine)."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

SP = ROOT / "data" / "spider" / "spider_data"
ITEMS = json.loads((ROOT / "data" / "spider_oir_n200.json").read_text())["items"][:32]
DB = SP / "database"
RUNS = ROOT / "runs" / "spider_sql_n32"
RESULTS = ROOT / "results"


def schema_text(db_id: str) -> str:
    con = sqlite3.connect(f"file:{DB / db_id / f'{db_id}.sqlite'}?mode=ro", uri=True)
    chunks = []
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"):
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
        chunks.append(f"{t}({', '.join(cols)})")
    con.close()
    return "\n".join(chunks)


def pack_one(cid, q, db_id, schema):
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. No other files.",
            "Write ONE sqlite SQL query that answers the question. Readable schema, plaintext DB names.",
            f"Format: SQL[{cid}]: <sql>",
            "",
            f"DB: {db_id}",
            f"SCHEMA:\n{schema}",
            f"QUESTION:\n{q}",
        ]
    )


def nnum(s) -> str:
    s = str(s).strip().rstrip(".")
    try:
        f = float(str(s).replace(",", ""))
        if abs(f - round(f)) < 1e-6:
            return str(int(round(f)))
        return f"{f:.4f}".rstrip("0").rstrip(".")
    except Exception:
        return re.sub(r"\s+", " ", str(s)).lower()


def build():
    iso = RUNS / "iso"
    iso.mkdir(parents=True, exist_ok=True)
    cases = []
    batch_items = []
    for i, it in enumerate(ITEMS):
        cid = f"SPSQL_{i}"
        sch = schema_text(it["db_id"])
        (iso / f"{cid}.txt").write_text(pack_one(cid, it["question"], it["db_id"], sch))
        batch_items.append((cid, it["question"], it["db_id"], sch))
        cases.append({"i": i, "id": cid, "db_id": it["db_id"], "question": it["question"], "gold": it["gold"], "gold_sql": it["query"]})
    lines = [
        "MODEL UNDER TEST. Read ONLY this file.",
        "For EACH id write: SQL[<id>]: <sqlite>",
        "Readable schema. Execute mentally is NOT required; we will run your SQL.",
        "",
    ]
    for cid, q, db_id, sch in batch_items:
        lines.append(f"##### ID {cid} #####\nDB: {db_id}\nSCHEMA:\n{sch}\nQUESTION:\n{q}\n")
    b = RUNS / "BATCH.txt"
    b.write_text("\n".join(lines))
    h = {"n": len(cases), "path": str(b), "iso_dir": str(iso), "cases": cases, "nonclaim": "Not a Spider leaderboard. SQL is executed in sqlite."}
    out = RESULTS / "spider_sql_n32_harness.json"
    out.write_text(json.dumps(h, indent=2))
    print(json.dumps({"n": len(cases), "out": str(out)}, indent=2))


def score(model: str):
    H = json.loads((RESULTS / "spider_sql_n32_harness.json").read_text())
    blob = ""
    d = RESULTS / f"spider_sql_n32_replies_{model}"
    if d.exists():
        blob = "\n".join(p.read_text() for p in d.rglob("*.txt"))
    rx = re.compile(r"SQL\[([^\]]+)\]:\s*(.+?)(?=\nSQL\[|\n#####|\Z)", re.I | re.S)
    # also fenced sql
    preds = {m.group(1): m.group(2).strip().rstrip(";").split("\n")[0] for m in rx.finditer(blob)}
    # salvage SELECT ... from raw files
    if d.exists():
        for p in d.rglob("*.txt"):
            cid = p.stem
            if cid in preds:
                continue
            m = re.search(r"(SELECT\b[\s\S]+?)(?:;|\Z)", p.read_text(), re.I)
            if m:
                preds[cid] = re.sub(r"\s+", " ", m.group(1)).strip()
    n = H["n"]
    oks, rows = [], []
    for c in H["cases"]:
        sql = preds.get(c["id"], "")
        ok = False
        err = "missing"
        got = None
        if sql:
            db = DB / c["db_id"] / f"{c['db_id']}.sqlite"
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                r = con.execute(sql).fetchall()
                if r and r[0][0] is not None:
                    got = r[0][0]
                    ok = nnum(got) == nnum(c["gold"])
                    err = None if ok else "mismatch"
                else:
                    err = "empty"
            except Exception as e:
                err = str(e)[:80]
            con.close()
        oks.append(ok)
        rows.append({"id": c["id"], "sql": sql[:160], "got": got, "gold": c["gold"], "ok": ok, "err": err})
    k = sum(oks)
    summary = {"score": f"{k}/{n}", "wilson": wilson(k, n), "exec_ok_parse": sum(1 for r in rows if r["sql"])}
    path = RESULTS / f"spider_sql_n32_{model}.json"
    path.write_text(json.dumps({"model": model, "n": n, "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else "auto")
    else:
        build()
