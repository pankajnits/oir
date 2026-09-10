#!/usr/bin/env python3
"""Spider Text-to-SQL baselines that EXECUTE in sqlite (not LLM-as-SQL).

1) HEURISTIC: schema-link + templates (avg/count/min/max/name WHERE cell)
2) Optional gold-SQL ENGINE already in baselines_oir.py

Not CodeS. Honest non-neural compiler + executor.
"""
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
ITEMS = json.loads((ROOT / "data" / "spider_oir_n200.json").read_text())["items"]
DB = SP / "database"


def nnum(s) -> str:
    s = str(s).strip().rstrip(".")
    try:
        f = float(s.replace(",", ""))
        if abs(f - round(f)) < 1e-6:
            return str(int(round(f)))
        return f"{f:.4f}".rstrip("0").rstrip(".")
    except Exception:
        return re.sub(r"\s+", " ", s).lower()


def schema(db_id: str):
    con = sqlite3.connect(f"file:{DB / db_id / f'{db_id}.sqlite'}?mode=ro", uri=True)
    tables = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"):
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
        tables[t] = cols
    fks = []
    for t, cols in tables.items():
        for row in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            # id, seq, table, from, to, ...
            fks.append((t, row[3], row[2], row[4]))
    con.close()
    return tables, fks


def pick_col(cols, cues):
    cl = [(c, c.lower()) for c in cols]
    for cue in cues:
        for c, lc in cl:
            if cue in lc:
                return c
    return cols[0] if cols else None


def heuristic_sql(question: str, db_id: str) -> str | None:
    tables, fks = schema(db_id)
    q = question.lower()
    # table mention
    tnames = sorted(tables, key=lambda t: -len(t))
    mentioned = [t for t in tnames if t.lower().replace("_", " ") in q or t.lower() in q]
    t0 = mentioned[0] if mentioned else tnames[0]
    cols = tables[t0]
    name_c = pick_col(cols, ["name", "title", "bname", "cname", "city"])
    if any(w in q for w in ["how many", "count", "number of"]):
        return f'SELECT COUNT(*) FROM "{t0}"'
    if "average" in q or "avg" in q:
        num = pick_col(cols, ["age", "balance", "amount", "earnings", "spent", "height", "rank", "year"])
        if num:
            return f'SELECT AVG("{num}") FROM "{t0}"'
    if any(w in q for w in ["sum", "total"]):
        num = pick_col(cols, ["amount", "spent", "balance", "earnings", "pounds", "ticket"])
        if num:
            return f'SELECT SUM("{num}") FROM "{t0}"'
    # JOIN if 2 tables mentioned or FK exists
    if len(mentioned) >= 2 or (fks and ("name" in q or "who" in q)):
        t1 = mentioned[1] if len(mentioned) >= 2 else (fks[0][2] if fks else None)
        if t1 and t1 in tables:
            # find fk
            fk = next((x for x in fks if {x[0], x[2]} == {t0, t1}), None)
            if fk is None:
                fk = next((x for x in fks if x[0] == t0 or x[2] == t0), None)
            if fk:
                a, af, b, bf = fk
                nc = pick_col(tables.get(t1, tables[t0]), ["name", "title", "city"])
                return f'SELECT "{t1}"."{nc}" FROM "{a}" JOIN "{b}" ON "{a}"."{af}" = "{b}"."{bf}" LIMIT 1'
    if name_c:
        return f'SELECT "{name_c}" FROM "{t0}" LIMIT 1'
    return f'SELECT * FROM "{t0}" LIMIT 1'


def exec_sql(db_id: str, sql: str):
    con = sqlite3.connect(f"file:{DB / db_id / f'{db_id}.sqlite'}?mode=ro", uri=True)
    try:
        rows = con.execute(sql).fetchall()
    except Exception as e:
        con.close()
        return None, str(e)
    con.close()
    if len(rows) == 1 and len(rows[0]) == 1 and rows[0][0] is not None:
        return rows[0][0], None
    if rows and rows[0][0] is not None:
        return rows[0][0], "multi"
    return None, "empty"


def main():
    k = 0
    rows = []
    for it in ITEMS:
        sql = heuristic_sql(it["question"], it["db_id"])
        got, err = exec_sql(it["db_id"], sql) if sql else (None, "no_sql")
        ok = got is not None and nnum(got) == nnum(it["gold"])
        k += int(ok)
        rows.append({"db": it["db_id"], "q": it["question"][:80], "sql": sql, "got": got, "gold": it["gold"], "ok": ok, "err": err})
    n = len(ITEMS)
    out = {
        "n": n,
        "HEURISTIC_SQL_EXEC": {"score": f"{k}/{n}", "wilson": wilson(k, n)},
        "note": "Schema-link templates executed in sqlite. Not CodeS. Not LLM-as-SQL.",
        "rows_head": rows[:12],
    }
    path = ROOT / "results" / "spider_heuristic_sql_n200.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["HEURISTIC_SQL_EXEC"], indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
