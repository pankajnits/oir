#!/usr/bin/env python3
"""Spider JOIN OIR: real questions, gold = sqlite execution denotation.

Mild vault: readable schema, sealed cells. Gold SQL rewritten with sealed literals.
Not a Spider leaderboard. n=12 small DBs from Spider dev (CC-BY-SA-4.0).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "spider_oir"
KEY = b"oir-spider-oir-v1"
ITEMS = json.loads((ROOT / "data" / "spider_oir_n12.json").read_text())["items"]
DBROOT = ROOT / "data" / "spider" / "spider_data" / "database"


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def dump_db(db_id: str) -> dict[str, tuple[list[str], list[list[str]]]]:
    db = DBROOT / db_id / f"{db_id}.sqlite"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if t.startswith("sqlite"):
            continue
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
        rows = [[("" if v is None else str(v)) for v in r] for r in con.execute(f'SELECT * FROM "{t}"')]
        out[t] = (cols, rows)
    con.close()
    return out


def render(tables, sealer=None):
    chunks = []
    for name, (h, rows) in tables.items():
        if sealer:
            body = [[sealer.atom(c) if c else sealer.atom("EMPTY") for c in row] for row in rows]
        else:
            body = rows
        chunks.append(f"TABLE {name}\n" + md_table(h, body))
    return "\n\n".join(chunks)


def cell_strings(tables) -> set[str]:
    s: set[str] = set()
    for _, (_h, rows) in tables.items():
        for row in rows:
            for c in row:
                if c and not re.fullmatch(r"-?\d+(?:\.\d+)?", c):
                    s.add(c)
    return s


def seal_sql(sql: str, sealer: EntitySeal, cells: set[str] | None = None) -> str:
    """Seal quoted string literals that match table cells. Do NOT HMAC integers
    (JOIN keys, LIMIT, HAVING COUNT >= 2, year filters)."""

    def repl(m: re.Match) -> str:
        q, body = m.group(1), m.group(2)
        if cells is None or body in cells:
            return q + sealer.atom(body) + q
        return m.group(0)

    return re.sub(r"(['\"])([^'\"]*)\1", repl, sql)


def pack(kind, header, items):
    tag = "ANSWER_PLAIN" if kind == "plain" else "ANSWER_SEALED"
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT tables only. No decrypt.",
        f"Format: {tag}[<id>]: <answer_or_UNKNOWN>",
        "Answer EVERY ID.",
        "",
        header,
        "",
    ]
    for cid, body, ctx in items:
        lines.append(f"##### ID {cid} #####\n{body}\n\nCONTEXT:\n{ctx}\n")
    return "\n".join(lines)


def build():
    sealer = EntitySeal(KEY)
    buckets = {k: [] for k in ("PLAIN_NL", "MILD_NL", "GOLD_SQL", "MODEL_SQL")}
    cases = []
    for i, it in enumerate(ITEMS):
        tables = dump_db(it["db_id"])
        gold = it["gold"]
        gold_seal = sealer.atom(gold)
        plain = render(tables)
        mild = render(tables, sealer)
        sql_s = seal_sql(it["query"], sealer, cell_strings(tables))
        q = it["question"]
        ids = {
            "PLAIN_NL": f"SP_PLAINNL_{i}",
            "MILD_NL": f"SP_MILDNL_{i}",
            "GOLD_SQL": f"SP_GOLDSQL_{i}",
            "MODEL_SQL": f"SP_MODELSQL_{i}",
        }
        buckets["PLAIN_NL"].append((ids["PLAIN_NL"], f"QUESTION:\n{q}", plain))
        buckets["MILD_NL"].append((ids["MILD_NL"], f"QUESTION:\n{sealer.text(q)}", mild))
        buckets["GOLD_SQL"].append(
            (ids["GOLD_SQL"], f"Execute this SQL over CONTEXT (cells are sealed):\n{sql_s}", mild)
        )
        buckets["MODEL_SQL"].append(
            (
                ids["MODEL_SQL"],
                f"Write SQL using readable headers, then the sealed answer.\nQUESTION:\n{q}",
                mild,
            )
        )
        cases.append(
            {
                "i": i,
                "db_id": it["db_id"],
                "question": q,
                "query": it["query"],
                "expect_plain": gold,
                "expect_seal": gold_seal,
                "ids": ids,
            }
        )
    RUNS.mkdir(parents=True, exist_ok=True)
    headers = {
        "PLAIN_NL": "ARM PLAIN_NL: Spider human question + plaintext sqlite dump. Return the execution answer.",
        "MILD_NL": "ARM MILD_NL: readable headers, sealed cells, token-HMAC question.",
        "GOLD_SQL": "ARM GOLD_SQL: gold Spider SQL with sealed string literals; LLM interprets markdown (not sqlite).",
        "MODEL_SQL": "ARM MODEL_SQL (G-Inc2): generate SQL, execute on sealed cells, return sealed answer.",
    }
    kinds = {"PLAIN_NL": "plain", "MILD_NL": "sealed", "GOLD_SQL": "sealed", "MODEL_SQL": "sealed"}
    paths = {}
    for arm, items in buckets.items():
        d = RUNS / f"{arm}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack(kinds[arm], headers[arm], items))
        paths[arm] = str(p)
    harness = {
        "n": len(cases),
        "suite": "spider_oir",
        "license": "CC-BY-SA-4.0 (Spider)",
        "paths": paths,
        "cases": cases,
        "nonclaim": "Not a Spider leaderboard. Small-DB slice. sqlite ENGINE_GOLD is the ceiling; GOLD_SQL is LLM-as-SQL.",
    }
    out = RESULTS / "spider_oir_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": len(cases), "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
