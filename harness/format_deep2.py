#!/usr/bin/env python3
"""Format-depth round 2: sealed JSON keys + live sqlite (engine + model SQL).

Round 1 (FORMAT_DEEP.md) left two confounds:
  - JSON3_NL 6/6 used English keys (employer/hq/country) — copy-and-walk
  - SQL3_PROG 6/6 was markdown tables, not executed sqlite

This suite:
  JSON_KEY_NOLEG — same nested graph; keys HMAC'd; START in V(G); no key legend
  JSON_KEY_LEG   — same + English→sealed-key legend
  SQL_MODEL      — schema only (no row dump); model writes SQL; we execute
  SQL_ENGINE     — gold 3-JOIN executed on the same sealed sqlite (no MUT)

Isolation required for JSON_KEY_* and SQL_MODEL.
Not G-Rev1. Seals ≠ confidentiality. Not a Spider leaderboard.
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
RUNS = ROOT / "runs" / "format_deep2"
KEY = b"oir-format-deep2-v1"
SEED = 20260814
N = 6
COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]

JSON_KEY_NAMES = ("employees", "orgs", "id", "employer", "hq", "city", "country")


def pack(header: str, body: str, *, fmt: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        f"{fmt}\n"
        "If more than one reading is possible, output UNKNOWN.\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def country_of(hq: str) -> str:
    return COUNTRIES[sum(map(ord, hq)) % len(COUNTRIES)]


def write(path: Path, header: str, body: str, *, fmt: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack(header, body, fmt=fmt))


def gold_sql(emp_id: str) -> str:
    return (
        "SELECT cities.country FROM employees "
        "JOIN orgs ON employees.org_id = orgs.org_id "
        "JOIN cities ON orgs.city_id = cities.city_id "
        f"WHERE employees.emp_id = '{emp_id}'"
    )


def build_db(path: Path, emp_rows, org_rows, city_rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE employees (emp_id TEXT, org_id TEXT)")
    con.execute("CREATE TABLE orgs (org_id TEXT, city_id TEXT)")
    con.execute("CREATE TABLE cities (city_id TEXT, country TEXT)")
    con.executemany("INSERT INTO employees VALUES (?, ?)", emp_rows)
    con.executemany("INSERT INTO orgs VALUES (?, ?)", org_rows)
    con.executemany("INSERT INTO cities VALUES (?, ?)", city_rows)
    con.commit()
    con.close()


def exec_sql(db: Path, sql: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(sql).fetchall()
    finally:
        con.close()
    return rows


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    pool = [r for r in graph.records if r not in recs]
    sealer = EntitySeal(KEY)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
        for p in RUNS.rglob("*.sqlite"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    kmap = {name: sealer.atom(f"JSONKEY:{name}") for name in JSON_KEY_NAMES}
    cases = []
    engine_ok = 0

    def add(arm, i, cid, gold, extra=None):
        rec = {"arm": arm, "i": i, "id": cid, "gold": gold, **(extra or {})}
        cases.append(rec)
        return rec

    for i, row in enumerate(recs):
        person, company, hq = row["person"], row["company"], row["hq"]
        country = country_of(hq)
        others = []
        for d in rng.sample(pool, 2):
            others.append(
                {
                    "person": d["person"],
                    "company": d["company"],
                    "hq": d["hq"],
                    "country": country_of(d["hq"]),
                }
            )
        pS, cS, hS, nS = sealer.atom(person), sealer.atom(company), sealer.atom(hq), sealer.atom(country)

        employees = [{kmap["id"]: pS, kmap["employer"]: cS}]
        orgs = [{kmap["id"]: cS, kmap["hq"]: {kmap["city"]: hS, kmap["country"]: nS}}]
        for o in others:
            employees.append(
                {kmap["id"]: sealer.atom(o["person"]), kmap["employer"]: sealer.atom(o["company"])}
            )
            orgs.append(
                {
                    kmap["id"]: sealer.atom(o["company"]),
                    kmap["hq"]: {
                        kmap["city"]: sealer.atom(o["hq"]),
                        kmap["country"]: sealer.atom(o["country"]),
                    },
                }
            )
        rng.shuffle(employees)
        rng.shuffle(orgs)
        ctx_json = json.dumps({kmap["employees"]: employees, kmap["orgs"]: orgs}, indent=2)
        legend = "KEY_LEGEND (English name → sealed JSON key):\n" + "\n".join(
            f"{name} = {kmap[name]}" for name in JSON_KEY_NAMES
        )
        cid_jn, cid_jl = f"FD2_JSON_KEY_NOLEG_{i}", f"FD2_JSON_KEY_LEG_{i}"
        p_jn = RUNS / "JSON_KEY_NOLEG" / f"item_{i}" / "prompt.txt"
        p_jl = RUNS / "JSON_KEY_LEG" / f"item_{i}" / "prompt.txt"
        q = f"START {pS}\nFrom START, return the nested country atom."
        write(
            p_jn,
            "ARM JSON_KEY_NOLEG: nested JSON; keys AND values sealed. No key legend. No JOIN. Start token is in CONTEXT.",
            f"##### ID {cid_jn} #####\n{q}\n\nCONTEXT:\n{ctx_json}\n",
            fmt="Format: ANSWER_SEALED[<id>]: <token_or_UNKNOWN>",
        )
        write(
            p_jl,
            "ARM JSON_KEY_LEG: same sealed-key JSON + English→key legend. No JOIN. Start token is in CONTEXT.",
            f"##### ID {cid_jl} #####\n{legend}\n\n{q}\n\nCONTEXT:\n{ctx_json}\n",
            fmt="Format: ANSWER_SEALED[<id>]: <token_or_UNKNOWN>",
        )
        add("JSON_KEY_NOLEG", i, cid_jn, nS, {"iso": True, "path": str(p_jn), "surface": "json_keys", "trap": hS})
        add("JSON_KEY_LEG", i, cid_jl, nS, {"iso": True, "path": str(p_jl), "surface": "json_keys", "trap": hS})

        emp_rows = [(pS, cS)]
        org_rows = [(cS, hS)]
        city_rows = [(hS, nS)]
        for o in others:
            emp_rows.append((sealer.atom(o["person"]), sealer.atom(o["company"])))
            org_rows.append((sealer.atom(o["company"]), sealer.atom(o["hq"])))
            city_rows.append((sealer.atom(o["hq"]), sealer.atom(o["country"])))
        rng.shuffle(emp_rows)
        rng.shuffle(org_rows)
        rng.shuffle(city_rows)
        db = RUNS / "db" / f"item_{i}.sqlite"
        build_db(db, emp_rows, org_rows, city_rows)
        gsql = gold_sql(pS)
        got = exec_sql(db, gsql)
        engine_hit = bool(got) and got[0][0] == nS
        engine_ok += int(engine_hit)
        add(
            "SQL_ENGINE",
            i,
            f"FD2_SQL_ENGINE_{i}",
            nS,
            {
                "iso": False,
                "surface": "sqlite_live",
                "db": str(db),
                "gold_sql": gsql,
                "engine_ok": engine_hit,
                "pred": got[0][0] if got else None,
            },
        )
        cid_sm = f"FD2_SQL_MODEL_{i}"
        p_sm = RUNS / "SQL_MODEL" / f"item_{i}" / "prompt.txt"
        write(
            p_sm,
            "ARM SQL_MODEL: live sqlite. You do not see rows. Write ONE query; we execute it.",
            (
                f"##### ID {cid_sm} #####\n"
                "SCHEMA:\n"
                "employees(emp_id TEXT, org_id TEXT)\n"
                "orgs(org_id TEXT, city_id TEXT)\n"
                "cities(city_id TEXT, country TEXT)\n\n"
                "QUESTION:\n"
                f"Return cities.country for the employee whose emp_id is {pS}.\n"
            ),
            fmt="Format: SQL[<id>]: <sqlite>",
        )
        add(
            "SQL_MODEL",
            i,
            cid_sm,
            nS,
            {"iso": True, "path": str(p_sm), "surface": "sqlite_live", "db": str(db), "gold_sql": gsql},
        )

    arms = {}
    for name in ("JSON_KEY_NOLEG", "JSON_KEY_LEG", "SQL_MODEL"):
        ids = [c["id"] for c in cases if c["arm"] == name]
        arms[name] = {
            "n": len(ids),
            "ids": ids,
            "iso": True,
            "item_paths": [c["path"] for c in cases if c["arm"] == name],
        }
    eng_ids = [c["id"] for c in cases if c["arm"] == "SQL_ENGINE"]
    arms["SQL_ENGINE"] = {"n": len(eng_ids), "ids": eng_ids, "iso": False, "engine": True}

    out = RESULTS / "format_deep2_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "format_deep2",
                "seed": SEED,
                "key_map": kmap,
                "engine_gold": f"{engine_ok}/{N}",
                "arms": arms,
                "cases": cases,
                "nonclaim": (
                    "JSON_KEY_NOLEG tests whether readable keys were necessary for JSON3_NL. "
                    "SQL_MODEL is schema-only 3-JOIN generation, not a Spider leaderboard. "
                    "SQL_ENGINE is gold SQL on sealed cells (no MUT). Not G-Rev1. Not confidentiality."
                ),
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "engine_gold": f"{engine_ok}/{N}", "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
