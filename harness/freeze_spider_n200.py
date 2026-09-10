#!/usr/bin/env python3
"""Freeze Spider JOIN slice: small DBs, 1-cell sqlite gold, seed 20260813.

Not a Spider leaderboard. CC-BY-SA-4.0.
"""
from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SP = ROOT / "data" / "spider" / "spider_data"
OUT = ROOT / "data" / "spider_oir_n200.json"
SEED = 20260813
MAX_CELLS = 250
N = 200


def cell_count(db_id: str) -> int | None:
    db = SP / "database" / db_id / f"{db_id}.sqlite"
    if not db.exists():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    n = 0
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if t.startswith("sqlite"):
            continue
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
        n += con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] * len(cols)
    con.close()
    return n


def exec_one_cell(db_id: str, sql: str) -> str | None:
    db = SP / "database" / db_id / f"{db_id}.sqlite"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.execute(sql)
        rows = cur.fetchall()
    except Exception:
        con.close()
        return None
    con.close()
    if len(rows) != 1 or len(rows[0]) != 1 or rows[0][0] is None:
        return None
    v = rows[0][0]
    return str(v)


def main():
    rows = []
    for split, name in [("dev", "dev.json"), ("train", "train_spider.json")]:
        for r in json.loads((SP / name).read_text()):
            sql = r.get("query") or ""
            if " join " not in sql.lower():
                continue
            rows.append((split, r["db_id"], r["question"], sql))

    rng = random.Random(SEED)
    rng.shuffle(rows)
    picked, seen_q, cells_cache = [], set(), {}
    skipped = {"cells": 0, "exec": 0, "dup": 0, "nodb": 0}
    for split, db_id, q, sql in rows:
        key = (db_id, q.strip().lower())
        if key in seen_q:
            skipped["dup"] += 1
            continue
        if db_id not in cells_cache:
            cells_cache[db_id] = cell_count(db_id)
        ncells = cells_cache[db_id]
        if ncells is None:
            skipped["nodb"] += 1
            continue
        if ncells > MAX_CELLS:
            skipped["cells"] += 1
            continue
        gold = exec_one_cell(db_id, sql)
        if gold is None:
            skipped["exec"] += 1
            continue
        seen_q.add(key)
        picked.append(
            {
                "db_id": db_id,
                "question": q,
                "query": sql,
                "gold": gold,
                "cells": ncells,
                "split": split,
            }
        )
        if len(picked) >= N:
            break

    OUT.write_text(
        json.dumps(
            {
                "source": "Spider train+dev JOIN, 1-cell sqlite gold, cells<=250",
                "license": "CC-BY-SA-4.0 (Spider)",
                "seed": SEED,
                "n": len(picked),
                "max_cells": MAX_CELLS,
                "skipped": skipped,
                "items": picked,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    dbs = sorted({x["db_id"] for x in picked})
    print(json.dumps({"n": len(picked), "dbs": len(dbs), "skipped": skipped, "out": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
