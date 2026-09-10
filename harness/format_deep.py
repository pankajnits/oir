#!/usr/bin/env python3
"""Deeper format confidence: nested JSON, vault English-ask, sqlite 3-join, ambiguous table columns.

Prior DOMAIN_FORMATS is batched 2-hop. This suite:
  JSON3     — nested 3-hop (person→org→city.country), isolated PROG vs NL
  VAULT_EN  — readable keys, sealed values, *English name* in Q:
              NOLEGEND (product fail) vs LEGEND (name→token binder)
  SQL3      — three markdown tables, JOIN program (batched ceiling)
  TAB_AMBIG — two city columns; PROG names city_primary; NL underspecified

Isolation required for JSON3 / VAULT_EN / TAB_AMBIG_NL.
Not G-Rev1. Seals ≠ confidentiality.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter
from oir.adapters import load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "format_deep"
KEY = b"oir-format-deep-v1"
SEED = 20260814
N = 6
COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]


def pack(header: str, body: str, *, sealed: bool) -> str:
    tag = "ANSWER_SEALED" if sealed else "ANSWER_PLAIN"
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        f"Format: {tag}[<id>]: <token_or_UNKNOWN>\n"
        "If more than one reading is possible, output UNKNOWN.\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def country_of(hq: str) -> str:
    return COUNTRIES[sum(map(ord, hq)) % len(COUNTRIES)]


def english_name(person: str) -> str:
    return person.replace("_", " ")


def write(path: Path, header: str, body: str, *, sealed: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack(header, body, sealed=sealed))


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
    RUNS.mkdir(parents=True, exist_ok=True)

    arms, cases = {}, []

    def add_case(arm, i, cid, gold, extra=None):
        rec = {"arm": arm, "i": i, "id": cid, "gold": gold, **(extra or {})}
        cases.append(rec)
        return rec

    json3_prog_ids, json3_nl_ids = [], []
    vault_nl_ids, vault_leg_ids = [], []
    tab_nl_ids = []
    sql_chunks = ["Follow JOIN over the three tables. Return the final sealed country atom.\n\n"]
    sql_ids = []
    tab_prog_chunks = [
        "JOIN returns city_primary, not city_secondary. Output the sealed city_primary only.\n\n"
    ]
    tab_prog_ids = []

    for i, row in enumerate(recs):
        person, company, hq = row["person"], row["company"], row["hq"]
        country = country_of(hq)
        distractors = rng.sample(pool, 2)
        others = []
        for d in distractors:
            others.append(
                {
                    "person": d["person"],
                    "company": d["company"],
                    "hq": d["hq"],
                    "country": country_of(d["hq"]),
                }
            )
        billing = others[0]["hq"]  # trap city
        pS, cS, hS, nS = sealer.atom(person), sealer.atom(company), sealer.atom(hq), sealer.atom(country)
        bS = sealer.atom(billing)

        # --- nested JSON 3-hop ---
        employees = [{"id": pS, "employer": cS}]
        orgs = [
            {
                "id": cS,
                "hq": {"city": hS, "country": nS},
            }
        ]
        for o in others:
            employees.append({"id": sealer.atom(o["person"]), "employer": sealer.atom(o["company"])})
            orgs.append(
                {
                    "id": sealer.atom(o["company"]),
                    "hq": {
                        "city": sealer.atom(o["hq"]),
                        "country": sealer.atom(o["country"]),
                    },
                }
            )
        rng.shuffle(employees)
        rng.shuffle(orgs)
        ctx_json = json.dumps({"employees": employees, "orgs": orgs}, indent=2)
        prog3 = (
            "JOIN_QUERY\n"
            f"START {pS}\n"
            "Follow employees[].id → employees[].employer → orgs[].id → orgs[].hq.country\n"
            "Return the nested country atom."
        )
        cid_jp, cid_jn = f"FD_JSON3_PROG_{i}", f"FD_JSON3_NL_{i}"
        json3_prog_ids.append(cid_jp)
        json3_nl_ids.append(cid_jn)
        p_jp = RUNS / "JSON3_PROG" / f"item_{i}" / "prompt.txt"
        p_jn = RUNS / "JSON3_NL" / f"item_{i}" / "prompt.txt"
        write(
            p_jp,
            "ARM JSON3_PROG: nested sealed JSON (hq object) + JOIN. One quiz.",
            f"##### ID {cid_jp} #####\n{prog3}\n\nCONTEXT:\n{ctx_json}\n",
            sealed=True,
        )
        write(
            p_jn,
            "ARM JSON3_NL: nested sealed JSON. No JOIN. One quiz. Start token is in CONTEXT.",
            f"##### ID {cid_jn} #####\nSTART {pS}\nFrom START, return the nested country atom.\n\nCONTEXT:\n{ctx_json}\n",
            sealed=True,
        )
        add_case("JSON3_PROG", i, cid_jp, nS, {"iso": True, "path": str(p_jp), "surface": "json_nested"})
        add_case("JSON3_NL", i, cid_jn, nS, {"iso": True, "path": str(p_jn), "surface": "json_nested"})

        # --- vault English ask (2-hop HQ), readable keys, industrial tok ---
        def tok(x):
            return "vault:v1:" + sealer.atom(x)

        people = {tok(person): {"company": tok(company)}}
        companies = {tok(company): {"hq_city": tok(hq)}}
        for o in others:
            people[tok(o["person"])] = {"company": tok(o["company"])}
            companies[tok(o["company"])] = {"hq_city": tok(o["hq"])}
        ctx_vault = json.dumps({"people": people, "companies": companies}, indent=2)
        gold_v = tok(hq)
        en = english_name(person)
        q_en = (
            f"Where is the headquarters city of the company associated with {en}?\n"
            "Return the vault token for that city."
        )
        legend = f"LEGEND (plaintext name → vault token):\n{en} = {tok(person)}"
        cid_vn, cid_vl = f"FD_VAULT_NOLEG_{i}", f"FD_VAULT_LEG_{i}"
        vault_nl_ids.append(cid_vn)
        vault_leg_ids.append(cid_vl)
        p_vn = RUNS / "VAULT_NOLEG" / f"item_{i}" / "prompt.txt"
        p_vl = RUNS / "VAULT_LEG" / f"item_{i}" / "prompt.txt"
        write(
            p_vn,
            "ARM VAULT_NOLEG: readable JSON keys, vault:v1 values. English name in QUESTION. No legend. No JOIN.",
            f"##### ID {cid_vn} #####\nQUESTION:\n{q_en}\n\nCONTEXT:\n{ctx_vault}\n",
            sealed=True,
        )
        write(
            p_vl,
            "ARM VAULT_LEG: same vault JSON + name→token legend. English QUESTION. No JOIN.",
            f"##### ID {cid_vl} #####\n{legend}\n\nQUESTION:\n{q_en}\n\nCONTEXT:\n{ctx_vault}\n",
            sealed=True,
        )
        add_case("VAULT_NOLEG", i, cid_vn, gold_v, {"iso": True, "path": str(p_vn), "surface": "vault", "plain_name": en})
        add_case("VAULT_LEG", i, cid_vl, gold_v, {"iso": True, "path": str(p_vl), "surface": "vault", "plain_name": en})

        # --- sqlite-style 3 tables ---
        emp_rows = [[pS, cS]]
        org_rows = [[cS, hS]]
        city_rows = [[hS, nS]]
        for o in others:
            emp_rows.append([sealer.atom(o["person"]), sealer.atom(o["company"])])
            org_rows.append([sealer.atom(o["company"]), sealer.atom(o["hq"])])
            city_rows.append([sealer.atom(o["hq"]), sealer.atom(o["country"])])
        rng.shuffle(emp_rows)
        rng.shuffle(org_rows)
        rng.shuffle(city_rows)
        ctx_sql = (
            "TABLE employees\n"
            + md_table(["emp_id", "org_id"], emp_rows)
            + "\n\nTABLE orgs\n"
            + md_table(["org_id", "city_id"], org_rows)
            + "\n\nTABLE cities\n"
            + md_table(["city_id", "country"], city_rows)
        )
        cid_sp = f"FD_SQL3_PROG_{i}"
        sql_ids.append(cid_sp)
        prog_sql = (
            "JOIN_QUERY\n"
            f"START employees.emp_id = {pS}\n"
            "JOIN employees.org_id = orgs.org_id\n"
            "JOIN orgs.city_id = cities.city_id\n"
            "RETURN cities.country"
        )
        sql_chunks.append(f"##### ID {cid_sp} #####\n{prog_sql}\n\nCONTEXT:\n{ctx_sql}\n")
        add_case("SQL3_PROG", i, cid_sp, nS, {"iso": False, "surface": "sqlite_md"})

        # --- ambiguous table columns ---
        people_rows = [[pS, cS]]
        co_rows = [[cS, hS, bS]]
        for o in others:
            people_rows.append([sealer.atom(o["person"]), sealer.atom(o["company"])])
            co_rows.append(
                [sealer.atom(o["company"]), sealer.atom(o["hq"]), sealer.atom(country_of(o["hq"]))]
            )
        rng.shuffle(people_rows)
        rng.shuffle(co_rows)
        ctx_tab = (
            "TABLE people\n"
            + md_table(["person", "company"], people_rows)
            + "\n\nTABLE companies\n"
            + md_table(["company", "city_primary", "city_secondary"], co_rows)
        )
        cid_tn, cid_tp = f"FD_TAB_NL_{i}", f"FD_TAB_PROG_{i}"
        tab_nl_ids.append(cid_tn)
        tab_prog_ids.append(cid_tp)
        p_tn = RUNS / "TAB_NL" / f"item_{i}" / "prompt.txt"
        write(
            p_tn,
            "ARM TAB_NL: two city columns. No JOIN. One quiz. If more than one city reading is possible, UNKNOWN.",
            f"##### ID {cid_tn} #####\nSTART {pS}\nReturn the city of this person's company.\n\nCONTEXT:\n{ctx_tab}\n",
            sealed=True,
        )
        add_case(
            "TAB_NL",
            i,
            cid_tn,
            hS,
            {"iso": True, "path": str(p_tn), "surface": "table", "trap": bS, "allow_unknown": True},
        )
        tab_prog_chunks.append(
            f"##### ID {cid_tp} #####\n"
            f"JOIN_QUERY\nSTART {pS}\n"
            "JOIN people.company = companies.company\nRETURN companies.city_primary\n\n"
            f"CONTEXT:\n{ctx_tab}\n"
        )
        add_case("TAB_PROG", i, cid_tp, hS, {"iso": False, "surface": "table", "trap": bS})

    def arm_iso(name, ids, glob):
        arms[name] = {
            "n": len(ids),
            "ids": ids,
            "iso": True,
            "item_paths": [str(p) for p in sorted((RUNS / glob).rglob("prompt.txt"))],
        }

    arm_iso("JSON3_PROG", json3_prog_ids, "JSON3_PROG")
    arm_iso("JSON3_NL", json3_nl_ids, "JSON3_NL")
    arm_iso("VAULT_NOLEG", vault_nl_ids, "VAULT_NOLEG")
    arm_iso("VAULT_LEG", vault_leg_ids, "VAULT_LEG")
    arm_iso("TAB_NL", tab_nl_ids, "TAB_NL")

    bp = RUNS / "SQL3_PROG_BATCH" / "BATCH.txt"
    write(bp, "ARM SQL3_PROG: 3 sealed-cell tables, readable headers, JOIN. Answer EVERY ID.", "\n".join(sql_chunks), sealed=True)
    arms["SQL3_PROG"] = {"n": len(sql_ids), "ids": sql_ids, "iso": False, "batch": str(bp)}

    bp2 = RUNS / "TAB_PROG_BATCH" / "BATCH.txt"
    write(
        bp2,
        "ARM TAB_PROG: two city columns; JOIN returns city_primary. Answer EVERY ID.",
        "\n".join(tab_prog_chunks),
        sealed=True,
    )
    arms["TAB_PROG"] = {"n": len(tab_prog_ids), "ids": tab_prog_ids, "iso": False, "batch": str(bp2)}

    out = RESULTS / "format_deep_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "format_deep",
                "seed": SEED,
                "arms": arms,
                "cases": cases,
                "nonclaim": (
                    "VAULT_NOLEG fail is missing name→token binder, not 'vaults don't work'. "
                    "TAB_NL UNKNOWN is allowed (two city columns). Not G-Rev1. Not confidentiality."
                ),
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "iso": sum(1 for c in cases if c.get("iso")), "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
