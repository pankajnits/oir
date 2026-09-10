#!/usr/bin/env python3
"""Product-picture demo: a layer between the app and the LLM.

App keeps plaintext. Layer seals question + vault (keys AND values),
attaches PROG, never sends a name→token legend to the model.
LLM answers in seals. Layer unseals for the app.

Not G-Rev1. Seals ≠ confidentiality (the layer still has the key).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal
from oir.adapters import load_ceo_hq_graph
from grev1_fullq_prog import seal_question

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "seal_layer_demo"
KEY = b"oir-seal-layer-demo-v1"
COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]


def country_of(hq: str) -> str:
    return COUNTRIES[sum(map(ord, hq)) % len(COUNTRIES)]


def seal_json(obj, sealer: EntitySeal):
    if isinstance(obj, dict):
        return {sealer.atom(k): seal_json(v, sealer) for k, v in obj.items()}
    if isinstance(obj, list):
        return [seal_json(v, sealer) for v in obj]
    if isinstance(obj, str):
        return sealer.atom(obj)
    return obj


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    row = graph.records[0]
    person, company, hq = row["person"], row["company"], row["hq"]
    country = country_of(hq)
    decoy = graph.records[1]
    decoy_c = country_of(decoy["hq"])

    sealer = EntitySeal(KEY)

    app_vault = {
        "employees": [
            {"id": decoy["person"], "employer": decoy["company"]},
            {"id": person, "employer": company},
        ],
        "orgs": [
            {
                "id": decoy["company"],
                "hq": {"city": decoy["hq"], "country": decoy_c},
            },
            {"id": company, "hq": {"city": hq, "country": country}},
        ],
    }
    app_question = f"What country is the HQ of {person.replace('_', ' ')} in?"

    sealed_vault = seal_json(app_vault, sealer)
    start = sealer.atom(person)
    k_emp = sealer.atom("employees")
    k_orgs = sealer.atom("orgs")
    k_id = sealer.atom("id")
    k_employer = sealer.atom("employer")
    k_hq = sealer.atom("hq")
    k_country = sealer.atom("country")
    sealed_question = seal_question(f"What country is the HQ of {start} in?", sealer, {start})

    prog = (
        f"JOIN_QUERY\n"
        f"START {start}\n"
        f"In array {k_emp}, match {k_id} = START, take {k_employer}.\n"
        f"In array {k_orgs}, match {k_id} = that employer, take {k_hq}.{k_country}.\n"
        f"Return that atom."
    )

    t_emp, t_org, t_city = sealer.atom("employees"), sealer.atom("orgs"), sealer.atom("cities")
    c_id, c_org = sealer.atom("id"), sealer.atom("org_id")
    c_city, c_country = sealer.atom("city_id"), sealer.atom("country")
    db = RUNS / "vault.sqlite"
    RUNS.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute(f'CREATE TABLE "{t_emp}" ("{c_id}" TEXT, "{c_org}" TEXT)')
    con.execute(f'CREATE TABLE "{t_org}" ("{c_id}" TEXT, "{c_city}" TEXT)')
    con.execute(f'CREATE TABLE "{t_city}" ("{c_id}" TEXT, "{c_country}" TEXT)')
    con.execute(
        f'INSERT INTO "{t_emp}" VALUES (?,?)',
        (sealer.atom(person), sealer.atom(company)),
    )
    con.execute(
        f'INSERT INTO "{t_emp}" VALUES (?,?)',
        (sealer.atom(decoy["person"]), sealer.atom(decoy["company"])),
    )
    con.execute(f'INSERT INTO "{t_org}" VALUES (?,?)', (sealer.atom(company), sealer.atom(hq)))
    con.execute(
        f'INSERT INTO "{t_org}" VALUES (?,?)',
        (sealer.atom(decoy["company"]), sealer.atom(decoy["hq"])),
    )
    con.execute(f'INSERT INTO "{t_city}" VALUES (?,?)', (sealer.atom(hq), sealer.atom(country)))
    con.execute(
        f'INSERT INTO "{t_city}" VALUES (?,?)',
        (sealer.atom(decoy["hq"]), sealer.atom(decoy_c)),
    )
    con.commit()
    gold_sql = (
        f'SELECT C."{c_country}" FROM "{t_emp}" E '
        f'JOIN "{t_org}" O ON E."{c_org}" = O."{c_id}" '
        f'JOIN "{t_city}" C ON O."{c_city}" = C."{c_id}" '
        f'WHERE E."{c_id}" = \'{start}\''
    )
    engine_row = con.execute(gold_sql).fetchone()
    con.close()

    llm_prompt = (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[LAYER_VAULT_0]: <token_or_UNKNOWN>\n\n"
        "ARM LAYER_VAULT: layer bound the English name to START and token-HMAC'd the question. "
        "You never see plaintext names or English question words. Follow JOIN over sealed JSON keys.\n\n"
        f"##### ID LAYER_VAULT_0 #####\n"
        f"QUESTION (already sealed by the layer):\n{sealed_question}\n\n"
        f"{prog}\n\nCONTEXT:\n{json.dumps(sealed_vault, indent=2)}\n"
    )
    prompt_path = RUNS / "LAYER_VAULT" / "item_0" / "prompt.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(llm_prompt)

    gold = sealer.atom(country)
    leaked = (
        person in llm_prompt
        or person.replace("_", " ") in llm_prompt
        or company in llm_prompt
        or hq in llm_prompt
        or country in llm_prompt
    )
    show = {
        "nonclaim": "Layer has the HMAC key. LLM never sees plaintext. Not confidentiality vs the layer. Not G-Rev1.",
        "app_sees": {
            "question": app_question,
            "vault_plaintext": app_vault,
            "expected_plain": country,
        },
        "llm_sees": {
            "question": sealed_question,
            "start": start,
            "prog": prog,
            "vault_sealed": sealed_vault,
        },
        "gold_sealed": gold,
        "plaintext_in_llm_prompt": leaked,
        "engine_sqlite": {
            "sql": gold_sql,
            "got": engine_row[0] if engine_row else None,
            "ok": engine_row == (gold,),
        },
        "rev": sealer.rev,
        "prompt": str(prompt_path),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "seal_layer_demo.json").write_text(json.dumps(show, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {
                "app_q": app_question,
                "llm_q": sealed_question,
                "gold_plain": country,
                "gold_sealed": gold,
                "engine_ok": show["engine_sqlite"]["ok"],
                "plaintext_in_llm_prompt": leaked,
                "prompt": str(prompt_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    build()
