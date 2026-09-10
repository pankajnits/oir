#!/usr/bin/env python3
"""Format-depth round 4: HMAC SQL *table* names (closes GPT column-NOLEG leak).

Round 3 left table names English (employees/orgs/cities); GPT NOLEG 4/6 used that.
This suite seals tables AND columns. Schema listing order is shuffled so
'last table' is not a country crib.

Arms:
  SQL_TAB_NOLEG — HMAC tables+columns; English Q; no legend (iso)
  SQL_TAB_LEG   — same + English→table/column legend (iso)
  SQL_TAB_PROG  — JOIN names sealed tables/columns (iso)
  SQL_TAB_ENGINE — gold SQL (no MUT)

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
RUNS = ROOT / "runs" / "format_deep4"
KEY = b"oir-format-deep2-v1"
SEED = 20260814
N = 6
COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]
COL_NAMES = ("emp_id", "org_id", "city_id", "country")
TAB_NAMES = ("employees", "orgs", "cities")


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


def gold_sql(tmap, cmap, emp_id: str) -> str:
    te, to, tc = (qid(tmap[k]) for k in TAB_NAMES)
    e, o, c, n = (qid(cmap[k]) for k in COL_NAMES)
    return (
        f"SELECT {tc}.{n} FROM {te} "
        f"JOIN {to} ON {te}.{o} = {to}.{o} "
        f"JOIN {tc} ON {to}.{c} = {tc}.{c} "
        f"WHERE {te}.{e} = '{emp_id}'"
    )


def build_db(path: Path, tmap, cmap, emp_rows, org_rows, city_rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    te, to, tc = tmap["employees"], tmap["orgs"], tmap["cities"]
    e, o, ci, n = cmap["emp_id"], cmap["org_id"], cmap["city_id"], cmap["country"]
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE {qid(te)} ({qid(e)} TEXT, {qid(o)} TEXT)")
    con.execute(f"CREATE TABLE {qid(to)} ({qid(o)} TEXT, {qid(ci)} TEXT)")
    con.execute(f"CREATE TABLE {qid(tc)} ({qid(ci)} TEXT, {qid(n)} TEXT)")
    con.executemany(f"INSERT INTO {qid(te)} VALUES (?, ?)", emp_rows)
    con.executemany(f"INSERT INTO {qid(to)} VALUES (?, ?)", org_rows)
    con.executemany(f"INSERT INTO {qid(tc)} VALUES (?, ?)", city_rows)
    con.commit()
    con.close()


def exec_sql(db: Path, sql: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def schema_text(tmap, cmap, rng: random.Random) -> str:
    blocks = [
        f"{tmap['employees']}({cmap['emp_id']} TEXT, {cmap['org_id']} TEXT)",
        f"{tmap['orgs']}({cmap['org_id']} TEXT, {cmap['city_id']} TEXT)",
        f"{tmap['cities']}({cmap['city_id']} TEXT, {cmap['country']} TEXT)",
    ]
    rng.shuffle(blocks)
    return "SCHEMA:\n" + "\n".join(blocks) + "\n"


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

    cmap = {name: sealer.atom(f"SQLCOL:{name}") for name in COL_NAMES}
    tmap = {name: sealer.atom(f"SQLTAB:{name}") for name in TAB_NAMES}
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
        build_db(db, tmap, cmap, emp_rows, org_rows, city_rows)
        gsql = gold_sql(tmap, cmap, pS)
        got = exec_sql(db, gsql)
        engine_hit = bool(got) and got[0][0] == nS
        engine_ok += int(engine_hit)
        add(
            "SQL_TAB_ENGINE",
            i,
            f"FD4_SQL_TAB_ENGINE_{i}",
            nS,
            {
                "iso": False,
                "surface": "sqlite_tabs",
                "db": str(db),
                "gold_sql": gsql,
                "engine_ok": engine_hit,
                "pred": got[0][0] if got else None,
            },
        )
        sch = schema_text(tmap, cmap, rng)
        legend = (
            "TAB_COL_LEGEND (English → sealed name):\n"
            + "\n".join(f"table {name} = {tmap[name]}" for name in TAB_NAMES)
            + "\n"
            + "\n".join(f"column {name} = {cmap[name]}" for name in COL_NAMES)
        )
        q_en = f"Return the country of the employee whose emp_id is {pS}."
        cid_n, cid_l, cid_p = f"FD4_SQL_TAB_NOLEG_{i}", f"FD4_SQL_TAB_LEG_{i}", f"FD4_SQL_TAB_PROG_{i}"
        p_n = RUNS / "SQL_TAB_NOLEG" / f"item_{i}" / "prompt.txt"
        p_l = RUNS / "SQL_TAB_LEG" / f"item_{i}" / "prompt.txt"
        p_p = RUNS / "SQL_TAB_PROG" / f"item_{i}" / "prompt.txt"
        write(
            p_n,
            "ARM SQL_TAB_NOLEG: live sqlite; HMAC table AND column names; English question. No legend. Write ONE query; we execute it.",
            f"##### ID {cid_n} #####\n{sch}\nQUESTION:\n{q_en}\n",
            fmt="Format: SQL[<id>]: <sqlite>  — or UNKNOWN if you cannot bind tables/columns.",
        )
        write(
            p_l,
            "ARM SQL_TAB_LEG: same HMAC tables+columns + English legend. Write ONE query; we execute it.",
            f"##### ID {cid_l} #####\n{legend}\n\n{sch}\nQUESTION:\n{q_en}\n",
            fmt="Format: SQL[<id>]: <sqlite>",
        )
        te, to, tc = tmap["employees"], tmap["orgs"], tmap["cities"]
        e, o, c, n = cmap["emp_id"], cmap["org_id"], cmap["city_id"], cmap["country"]
        prog = (
            "JOIN_QUERY\n"
            f"START {pS} is {te}.{e}\n"
            f"JOIN {te}.{o} = {to}.{o}\n"
            f"JOIN {to}.{c} = {tc}.{c}\n"
            f"RETURN {tc}.{n}"
        )
        write(
            p_p,
            "ARM SQL_TAB_PROG: HMAC tables+columns; JOIN names the sealed identifiers. Write ONE query; we execute it.",
            f"##### ID {cid_p} #####\n{prog}\n\n{sch}\n",
            fmt="Format: SQL[<id>]: <sqlite>",
        )
        extra = {
            "iso": True,
            "surface": "sqlite_tabs",
            "db": str(db),
            "gold_sql": gsql,
            "trap": hS,
        }
        add("SQL_TAB_NOLEG", i, cid_n, nS, {**extra, "path": str(p_n)})
        add("SQL_TAB_LEG", i, cid_l, nS, {**extra, "path": str(p_l)})
        add("SQL_TAB_PROG", i, cid_p, nS, {**extra, "path": str(p_p)})

    arms = {}
    for name in ("SQL_TAB_NOLEG", "SQL_TAB_LEG", "SQL_TAB_PROG"):
        ids = [c["id"] for c in cases if c["arm"] == name]
        arms[name] = {
            "n": len(ids),
            "ids": ids,
            "iso": True,
            "item_paths": [c["path"] for c in cases if c["arm"] == name],
        }
    arms["SQL_TAB_ENGINE"] = {
        "n": N,
        "ids": [c["id"] for c in cases if c["arm"] == "SQL_TAB_ENGINE"],
        "iso": False,
        "engine": True,
    }
    out = RESULTS / "format_deep4_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "format_deep4",
                "seed": SEED,
                "tab_map": tmap,
                "col_map": cmap,
                "engine_gold": f"{engine_ok}/{N}",
                "arms": arms,
                "cases": cases,
                "nonclaim": (
                    "Closes table-name leak from SQL_COL_NOLEG. "
                    "SQL_TAB_NOLEG fail is missing table/column binder. "
                    "Not CodeS. Not G-Rev1. Not confidentiality."
                ),
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "engine_gold": f"{engine_ok}/{N}", "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
