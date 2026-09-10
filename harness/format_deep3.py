#!/usr/bin/env python3
"""Format-depth round 3: PATH over sealed JSON keys + HMAC SQL column names.

Open holes after format_deep2:
  - JSON_KEY_LEG restored GPT 6/6 but composer-2.5 UNKNOWN 6/6 — does PATH restore composer-2.5?
  - SQL_MODEL used readable headers — are English column names load-bearing?

Arms:
  JSON_KEY_PROG — sealed keys+values; JOIN names the sealed keys (iso)
  SQL_COL_NOLEG — HMAC column names; English 'country' in Q; schema-only SQL (iso)
  SQL_COL_LEG   — same + English→column legend (iso)
  SQL_COL_ENGINE — gold SQL on HMAC-named columns (no MUT)

Not G-Rev1. Not CodeS. Seals ≠ confidentiality.
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
RUNS = ROOT / "runs" / "format_deep3"
KEY = b"oir-format-deep2-v1"  # same graphs as JSON_KEY_* golds
SEED = 20260814
N = 6
COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]
JSON_KEY_NAMES = ("employees", "orgs", "id", "employer", "hq", "city", "country")
COL_NAMES = ("emp_id", "org_id", "city_id", "country")


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


def qid(name: str) -> str:
    return f'"{name}"'


def gold_sql(cmap, emp_id: str) -> str:
    e, o, c, n = (qid(cmap[k]) for k in ("emp_id", "org_id", "city_id", "country"))
    return (
        f"SELECT cities.{n} FROM employees "
        f"JOIN orgs ON employees.{o} = orgs.{o} "
        f"JOIN cities ON orgs.{c} = cities.{c} "
        f"WHERE employees.{e} = '{emp_id}'"
    )


def build_db(path: Path, cmap, emp_rows, org_rows, city_rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    e, o, ci, n = cmap["emp_id"], cmap["org_id"], cmap["city_id"], cmap["country"]
    con = sqlite3.connect(path)
    con.execute(f'CREATE TABLE employees ({qid(e)} TEXT, {qid(o)} TEXT)')
    con.execute(f'CREATE TABLE orgs ({qid(o)} TEXT, {qid(ci)} TEXT)')
    con.execute(f'CREATE TABLE cities ({qid(ci)} TEXT, {qid(n)} TEXT)')
    con.executemany(f"INSERT INTO employees VALUES (?, ?)", emp_rows)
    con.executemany(f"INSERT INTO orgs VALUES (?, ?)", org_rows)
    con.executemany(f"INSERT INTO cities VALUES (?, ?)", city_rows)
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
        for p in RUNS.rglob("*.sqlite"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    kmap = {name: sealer.atom(f"JSONKEY:{name}") for name in JSON_KEY_NAMES}
    cmap = {name: sealer.atom(f"SQLCOL:{name}") for name in COL_NAMES}
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
        cid_jp = f"FD3_JSON_KEY_PROG_{i}"
        p_jp = RUNS / "JSON_KEY_PROG" / f"item_{i}" / "prompt.txt"
        prog = (
            "JOIN_QUERY\n"
            f"START {pS}\n"
            f"In array {kmap['employees']}, match {kmap['id']} = START, take {kmap['employer']}.\n"
            f"In array {kmap['orgs']}, match {kmap['id']} = that employer, take {kmap['hq']}.{kmap['country']}.\n"
            "Return that atom."
        )
        write(
            p_jp,
            "ARM JSON_KEY_PROG: nested JSON; keys AND values sealed; JOIN names the sealed keys. One quiz.",
            f"##### ID {cid_jp} #####\n{prog}\n\nCONTEXT:\n{ctx_json}\n",
            fmt="Format: ANSWER_SEALED[<id>]: <token_or_UNKNOWN>",
        )
        add("JSON_KEY_PROG", i, cid_jp, nS, {"iso": True, "path": str(p_jp), "surface": "json_keys", "trap": hS})

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
        build_db(db, cmap, emp_rows, org_rows, city_rows)
        gsql = gold_sql(cmap, pS)
        got = exec_sql(db, gsql)
        engine_hit = bool(got) and got[0][0] == nS
        engine_ok += int(engine_hit)
        add(
            "SQL_COL_ENGINE",
            i,
            f"FD3_SQL_COL_ENGINE_{i}",
            nS,
            {
                "iso": False,
                "surface": "sqlite_cols",
                "db": str(db),
                "gold_sql": gsql,
                "engine_ok": engine_hit,
                "pred": got[0][0] if got else None,
            },
        )
        schema = (
            "SCHEMA:\n"
            f"employees({cmap['emp_id']} TEXT, {cmap['org_id']} TEXT)\n"
            f"orgs({cmap['org_id']} TEXT, {cmap['city_id']} TEXT)\n"
            f"cities({cmap['city_id']} TEXT, {cmap['country']} TEXT)\n"
        )
        legend = "COL_LEGEND (English name → sealed column):\n" + "\n".join(
            f"{name} = {cmap[name]}" for name in COL_NAMES
        )
        q_en = f"Return the country of the employee whose emp_id is {pS}."
        cid_n, cid_l = f"FD3_SQL_COL_NOLEG_{i}", f"FD3_SQL_COL_LEG_{i}"
        p_n = RUNS / "SQL_COL_NOLEG" / f"item_{i}" / "prompt.txt"
        p_l = RUNS / "SQL_COL_LEG" / f"item_{i}" / "prompt.txt"
        write(
            p_n,
            "ARM SQL_COL_NOLEG: live sqlite; HMAC column names; English question. No column legend. Write ONE query; we execute it.",
            f"##### ID {cid_n} #####\n{schema}\nQUESTION:\n{q_en}\n",
            fmt="Format: SQL[<id>]: <sqlite>  — or UNKNOWN if you cannot bind the question to a column.",
        )
        write(
            p_l,
            "ARM SQL_COL_LEG: same HMAC columns + English→column legend. Write ONE query; we execute it.",
            f"##### ID {cid_l} #####\n{legend}\n\n{schema}\nQUESTION:\n{q_en}\n",
            fmt="Format: SQL[<id>]: <sqlite>",
        )
        extra = {
            "iso": True,
            "surface": "sqlite_cols",
            "db": str(db),
            "gold_sql": gsql,
            "trap": hS,
        }
        add("SQL_COL_NOLEG", i, cid_n, nS, {**extra, "path": str(p_n)})
        add("SQL_COL_LEG", i, cid_l, nS, {**extra, "path": str(p_l)})

    arms = {}
    for name in ("JSON_KEY_PROG", "SQL_COL_NOLEG", "SQL_COL_LEG"):
        ids = [c["id"] for c in cases if c["arm"] == name]
        arms[name] = {
            "n": len(ids),
            "ids": ids,
            "iso": True,
            "item_paths": [c["path"] for c in cases if c["arm"] == name],
        }
    arms["SQL_COL_ENGINE"] = {
        "n": N,
        "ids": [c["id"] for c in cases if c["arm"] == "SQL_COL_ENGINE"],
        "iso": False,
        "engine": True,
    }
    out = RESULTS / "format_deep3_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "format_deep3",
                "seed": SEED,
                "key_map": kmap,
                "col_map": cmap,
                "engine_gold": f"{engine_ok}/{N}",
                "arms": arms,
                "cases": cases,
                "nonclaim": (
                    "JSON_KEY_PROG is PATH over sealed keys, not G-Rev1. "
                    "SQL_COL_NOLEG fail is missing column binder, not 'SQL doesn't work'. "
                    "Not CodeS. Not confidentiality."
                ),
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "engine_gold": f"{engine_ok}/{N}", "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
