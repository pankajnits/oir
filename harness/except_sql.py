#!/usr/bin/env python3
"""EXCEPT / anti-join under sealed sqlite IDs.

L6 graph negation was batched 8/8 with handles. This suite is the industrial cell:
live sqlite, sealed TEXT ids, unique outsider (gold) vs same-org colleague (trap).

Arms:
  EXCEPT_ENGINE — gold EXCEPT SQL executed (no MUT)
  EXCEPT_MODEL  — schema only; model writes SQL; we execute (iso)
  EXCEPT_NL     — markdown dump, English NOT, no SQL (iso)
  EXCEPT_PROG   — gold EXCEPT over the same dump (batched ceiling)

Not G-Rev1. Not a Spider leaderboard. Seals ≠ confidentiality.
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal
from oir.adapters import load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "except_sql"
KEY = b"oir-except-sql-v1"
SEED = 20260814
N = 6


def pack(header: str, body: str, *, fmt: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        f"{fmt}\n"
        "If more than one reading is possible, output UNKNOWN.\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def write(path: Path, header: str, body: str, *, fmt: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack(header, body, fmt=fmt))


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def gold_sql(start: str) -> str:
    return (
        "SELECT emp_id FROM employees "
        "WHERE emp_id != "
        f"'{start}' "
        "EXCEPT "
        "SELECT emp_id FROM employees WHERE org_id = ("
        f"SELECT org_id FROM employees WHERE emp_id = '{start}'"
        ")"
    )


def build_db(path: Path, emp_rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE employees (emp_id TEXT, org_id TEXT)")
    con.executemany("INSERT INTO employees VALUES (?, ?)", emp_rows)
    con.commit()
    con.close()


def exec_sql(db: Path, sql: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    pool = [r for r in graph.records if r not in recs]
    sealer = EntitySeal(KEY)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
        for p in RUNS.rglob("BATCH.txt"):
            p.unlink()
        for p in RUNS.rglob("*.sqlite"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    cases = []
    engine_ok = 0
    prog_chunks = [
        "Follow the EXCEPT. Return the remaining sealed emp_id.\n\n"
    ]

    def add(arm, i, cid, gold, extra=None):
        rec = {"arm": arm, "i": i, "id": cid, "gold": gold, **(extra or {})}
        cases.append(rec)
        return rec

    for i, row in enumerate(recs):
        distractors = rng.sample(pool, 2)
        start_p, start_org = row["person"], row["company"]
        colleague_p = distractors[0]["person"]
        outsider_p, outsider_org = distractors[1]["person"], distractors[1]["company"]
        # Force colleague into START's org (anti-join trap); outsider unique other org.
        sE, sO = sealer.atom(start_p), sealer.atom(start_org)
        cE, cO = sealer.atom(colleague_p), sO
        oE, oO = sealer.atom(outsider_p), sealer.atom(outsider_org)
        emp_rows = [(sE, sO), (cE, cO), (oE, oO)]
        rng.shuffle(emp_rows)
        db = RUNS / "db" / f"item_{i}.sqlite"
        build_db(db, emp_rows)
        gsql = gold_sql(sE)
        got = exec_sql(db, gsql)
        engine_hit = bool(got) and got[0][0] == oE and len(got) == 1
        engine_ok += int(engine_hit)

        add(
            "EXCEPT_ENGINE",
            i,
            f"EX_ENGINE_{i}",
            oE,
            {
                "iso": False,
                "surface": "sqlite_live",
                "db": str(db),
                "gold_sql": gsql,
                "engine_ok": engine_hit,
                "pred": got[0][0] if got else None,
                "trap": cE,
                "start": sE,
            },
        )

        cid_m = f"EX_MODEL_{i}"
        p_m = RUNS / "EXCEPT_MODEL" / f"item_{i}" / "prompt.txt"
        write(
            p_m,
            "ARM EXCEPT_MODEL: live sqlite. You do not see rows. Write ONE query; we execute it.",
            (
                f"##### ID {cid_m} #####\n"
                "SCHEMA:\n"
                "employees(emp_id TEXT, org_id TEXT)\n\n"
                "QUESTION:\n"
                f"Return the emp_id of the employee who does NOT work at the same org_id "
                f"as employee {sE}. Exclude {sE} itself.\n"
            ),
            fmt="Format: SQL[<id>]: <sqlite>",
        )
        add(
            "EXCEPT_MODEL",
            i,
            cid_m,
            oE,
            {
                "iso": True,
                "path": str(p_m),
                "surface": "sqlite_live",
                "db": str(db),
                "gold_sql": gsql,
                "trap": cE,
                "start": sE,
            },
        )

        dump = "TABLE employees\n" + md_table(["emp_id", "org_id"], emp_rows)
        cid_n = f"EX_NL_{i}"
        p_n = RUNS / "EXCEPT_NL" / f"item_{i}" / "prompt.txt"
        write(
            p_n,
            "ARM EXCEPT_NL: sealed cells, readable headers. No SQL. English NOT. One quiz.",
            (
                f"##### ID {cid_n} #####\n"
                f"START {sE}\n"
                "Return the emp_id of the employee who does NOT work at the same org_id as START. "
                "Exclude START itself.\n\n"
                f"CONTEXT:\n{dump}\n"
            ),
            fmt="Format: ANSWER_SEALED[<id>]: <token_or_UNKNOWN>",
        )
        add(
            "EXCEPT_NL",
            i,
            cid_n,
            oE,
            {"iso": True, "path": str(p_n), "surface": "sqlite_md", "trap": cE, "start": sE},
        )

        cid_p = f"EX_PROG_{i}"
        prog_chunks.append(
            f"##### ID {cid_p} #####\n"
            "EXCEPT_QUERY\n"
            f"SELECT emp_id FROM employees WHERE emp_id != {sE}\n"
            "EXCEPT\n"
            f"SELECT emp_id FROM employees WHERE org_id = (SELECT org_id FROM employees WHERE emp_id = {sE})\n\n"
            f"CONTEXT:\n{dump}\n"
        )
        add("EXCEPT_PROG", i, cid_p, oE, {"iso": False, "surface": "sqlite_md", "trap": cE, "start": sE})

    bp = RUNS / "EXCEPT_PROG_BATCH" / "BATCH.txt"
    write(
        bp,
        "ARM EXCEPT_PROG: sealed-cell table + EXCEPT program. Answer EVERY ID.",
        "\n".join(prog_chunks),
        fmt="Format: ANSWER_SEALED[<id>]: <token_or_UNKNOWN>",
    )

    arms = {}
    for name in ("EXCEPT_MODEL", "EXCEPT_NL"):
        ids = [c["id"] for c in cases if c["arm"] == name]
        arms[name] = {
            "n": len(ids),
            "ids": ids,
            "iso": True,
            "item_paths": [c["path"] for c in cases if c["arm"] == name],
        }
    arms["EXCEPT_ENGINE"] = {
        "n": N,
        "ids": [c["id"] for c in cases if c["arm"] == "EXCEPT_ENGINE"],
        "iso": False,
        "engine": True,
    }
    arms["EXCEPT_PROG"] = {
        "n": N,
        "ids": [c["id"] for c in cases if c["arm"] == "EXCEPT_PROG"],
        "iso": False,
        "batch": str(bp),
    }

    out = RESULTS / "except_sql_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "except_sql",
                "seed": SEED,
                "engine_gold": f"{engine_ok}/{N}",
                "arms": arms,
                "cases": cases,
                "nonclaim": (
                    "Anti-join over sealed emp/org IDs. Trap = same-org colleague. "
                    "EXCEPT_ENGINE is gold SQL (no MUT). Not G-Rev1. Not Spider leaderboard."
                ),
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "engine_gold": f"{engine_ok}/{N}", "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
