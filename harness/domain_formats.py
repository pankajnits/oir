#!/usr/bin/env python3
"""
Domain-format OIR: tables, JSON, vault tokens.

Same 2-hop join (person → company → HQ) rendered three ways.
We know exactly: what is sealed, what is asked, what gold is.

Arms (per domain):
  PLAIN_PROG  — readable symbols + explicit JOIN/PATH
  SEAL_PROG   — sealed atoms + same program over seals
  SEAL_NL     — sealed payload + sealed free NL (negative)

Vault extra:
  VAULT_MILD  — readable relation *keys*, sealed entity *values*, English Q using the person seal
                (industrial PII-vault pattern; milder than entity+relation seals)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter, path_program
from oir.adapters import ceo_hq_edges, load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "domain_formats"
KEY = b"oir-domain-formats-v1"
SEED = 20260813
N = 12


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def json_pretty(obj) -> str:
    return json.dumps(obj, indent=2)


def pack(fmt: str, header: str, items: list[tuple[str, str]]) -> str:
    tag = "ANSWER_PLAIN" if fmt == "plain" else "ANSWER_SEALED"
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No decrypt. No world knowledge.",
        f"Format: {tag}[<id>]: <token_or_UNKNOWN>",
        "Answer EVERY ID.",
        "",
        header,
        "",
    ]
    for cid, body in items:
        lines.append(f"##### ID {cid} #####\n{body}\n")
    return "\n".join(lines)


def render_table(person, company, hq, others: list[dict], *, seal=None):
    """Two tables requiring a join on company_id. Optional sealer for cells+headers."""

    def t(x: str) -> str:
        return seal.atom(x) if seal else x

    people_h = [t("person"), t("company")]
    co_h = [t("company"), t("hq_city")]
    people_rows = [[t(person), t(company)]]
    co_rows = [[t(company), t(hq)]]
    for o in others:
        people_rows.append([t(o["person"]), t(o["company"])])
        co_rows.append([t(o["company"]), t(o["hq"])])
    rng = random.Random(hash(person) & 0xFFFFFFFF)
    rng.shuffle(people_rows)
    rng.shuffle(co_rows)
    return (
        "TABLE people\n"
        + md_table(people_h, people_rows)
        + "\n\nTABLE companies\n"
        + md_table(co_h, co_rows)
    )


def render_json(person, company, hq, others: list[dict], *, seal=None, mild=False):
    """JSON objects. mild=True keeps relation keys readable, seals entity values only."""

    def e(x: str) -> str:
        return seal.atom(x) if seal else x

    def k(x: str) -> str:
        if not seal:
            return x
        return x if mild else seal.atom(x)

    people = {e(person): {k("company"): e(company)}}
    companies = {e(company): {k("hq_city"): e(hq)}}
    for o in others:
        people[e(o["person"])] = {k("company"): e(o["company"])}
        companies[e(o["company"])] = {k("hq_city"): e(o["hq"])}
    return json_pretty({"people": people, "companies": companies})


def render_vault(person, company, hq, others: list[dict], sealer: EntitySeal, *, strict: bool):
    """Vault tokens for entities; keys readable unless strict."""
    return render_json(person, company, hq, others, seal=sealer, mild=not strict)


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    pool = [r for r in graph.records if r not in recs]
    sealer = EntitySeal(KEY)

    domains = {
        "TABLE": {},
        "JSON": {},
        "VAULT": {},
    }
    # arm -> list of (cid, body)
    buckets: dict[str, list] = {
        "TABLE_PLAIN_PROG": [],
        "TABLE_SEAL_PROG": [],
        "TABLE_SEAL_NL": [],
        "TABLE_SEAL_BOTH": [],
        "JSON_PLAIN_PROG": [],
        "JSON_SEAL_PROG": [],
        "JSON_SEAL_NL": [],
        "JSON_SEAL_BOTH": [],
        "VAULT_MILD": [],
        "VAULT_STRICT_PROG": [],
        "VAULT_STRICT_NL": [],
        "VAULT_STRICT_BOTH": [],
    }
    cases = []

    for i, row in enumerate(recs):
        person, hq, company = row["person"], row["hq"], row["company"]
        distractors = rng.sample(pool, 2)
        others = [{"person": d["person"], "company": d["company"], "hq": d["hq"]} for d in distractors]

        # SealRouter gold on triples (entity+relation)
        edges = [
            (person, "company", company),
            (company, "hq_city", hq),
        ]
        for o in others:
            edges += [(o["person"], "company", o["company"]), (o["company"], "hq_city", o["hq"])]
        sealed = [sealer.triple(*e) for e in edges]
        gold_seal = sealer.atom(hq)
        outs = SealRouter(sealed).path(sealer.atom(person), [sealer.atom("company"), sealer.atom("hq_city")])
        assert list(dict.fromkeys(outs)) == [gold_seal], (outs, hq)

        prog_plain = (
            "JOIN_QUERY\n"
            f"START person={person}\n"
            "R1 company\n"
            "R2 hq_city\n"
            "Join people.company = companies.company; return hq_city."
        )
        prog_seal = (
            "JOIN_QUERY\n"
            f"START {sealer.atom(person)}\n"
            f"R1 {sealer.atom('company')}\n"
            f"R2 {sealer.atom('hq_city')}\n"
            "Execute the two-hop join; return final tail only."
        )
        q_plain = (
            f"Where is the headquarters city of the company that {person.replace('_', ' ')} is associated with?"
        )
        q_seal = sealer.text(q_plain)

        # --- TABLE ---
        tbl_plain = render_table(person, company, hq, others)
        tbl_seal = render_table(person, company, hq, others, seal=sealer)
        buckets["TABLE_PLAIN_PROG"].append(
            (f"DOM_TABLE_PLAIN_{i}", f"{prog_plain}\n\nCONTEXT:\n{tbl_plain}")
        )
        buckets["TABLE_SEAL_PROG"].append(
            (f"DOM_TABLE_SEALPROG_{i}", f"{prog_seal}\n\nCONTEXT:\n{tbl_seal}")
        )
        buckets["TABLE_SEAL_NL"].append(
            (f"DOM_TABLE_SEALNL_{i}", f"QUESTION:\n{q_seal}\n\nCONTEXT:\n{tbl_seal}")
        )
        buckets["TABLE_SEAL_BOTH"].append(
            (
                f"DOM_TABLE_SEALBOTH_{i}",
                f"{prog_seal}\n\nQUESTION:\n{q_seal}\n\nCONTEXT:\n{tbl_seal}",
            )
        )

        # --- JSON ---
        js_plain = render_json(person, company, hq, others)
        js_seal = render_json(person, company, hq, others, seal=sealer, mild=False)
        buckets["JSON_PLAIN_PROG"].append(
            (f"DOM_JSON_PLAIN_{i}", f"{prog_plain}\n\nCONTEXT:\n{js_plain}")
        )
        buckets["JSON_SEAL_PROG"].append(
            (f"DOM_JSON_SEALPROG_{i}", f"{prog_seal}\n\nCONTEXT:\n{js_seal}")
        )
        buckets["JSON_SEAL_NL"].append(
            (f"DOM_JSON_SEALNL_{i}", f"QUESTION:\n{q_seal}\n\nCONTEXT:\n{js_seal}")
        )
        buckets["JSON_SEAL_BOTH"].append(
            (
                f"DOM_JSON_SEALBOTH_{i}",
                f"{prog_seal}\n\nQUESTION:\n{q_seal}\n\nCONTEXT:\n{js_seal}",
            )
        )

        # --- VAULT ---
        vault_mild = render_vault(person, company, hq, others, sealer, strict=False)
        vault_strict = render_vault(person, company, hq, others, sealer, strict=True)
        mild_q = (
            f"Using readable keys company / hq_city, what is the hq_city of the company "
            f"linked from person token {sealer.atom(person)}?"
        )
        mild_prog = (
            "JOIN_QUERY (readable keys, sealed entity values)\n"
            f"START {sealer.atom(person)}\n"
            "R1 company\n"
            "R2 hq_city\n"
            "Return the sealed hq_city token."
        )
        buckets["VAULT_MILD"].append(
            (f"DOM_VAULT_MILD_{i}", f"{mild_prog}\n\nQUESTION:\n{mild_q}\n\nCONTEXT:\n{vault_mild}")
        )
        buckets["VAULT_STRICT_PROG"].append(
            (f"DOM_VAULT_STRICTPROG_{i}", f"{prog_seal}\n\nCONTEXT:\n{vault_strict}")
        )
        buckets["VAULT_STRICT_NL"].append(
            (f"DOM_VAULT_STRICTNL_{i}", f"QUESTION:\n{q_seal}\n\nCONTEXT:\n{vault_strict}")
        )
        buckets["VAULT_STRICT_BOTH"].append(
            (
                f"DOM_VAULT_STRICTBOTH_{i}",
                f"{prog_seal}\n\nQUESTION:\n{q_seal}\n\nCONTEXT:\n{vault_strict}",
            )
        )

        cases.append(
            {
                "i": i,
                "person": person,
                "company": company,
                "hq": hq,
                "expect_plain": hq,
                "expect_seal": gold_seal,
                "person_seal": sealer.atom(person),
                "company_seal": sealer.atom(company),
            }
        )

    RUNS.mkdir(parents=True, exist_ok=True)
    paths = {}
    headers = {
        "TABLE_PLAIN_PROG": "ARM TABLE/PLAIN_PROG: readable markdown tables + JOIN program.",
        "TABLE_SEAL_PROG": "ARM TABLE/SEAL_PROG: HMAC-sealed table cells AND headers + JOIN over seals.",
        "TABLE_SEAL_NL": "ARM TABLE/SEAL_NL: sealed tables + sealed NL (no program).",
        "TABLE_SEAL_BOTH": "ARM TABLE/SEAL_BOTH: sealed tables + sealed NL + JOIN program. Execute JOIN; ignore unreadability of QUESTION.",
        "JSON_PLAIN_PROG": "ARM JSON/PLAIN_PROG: readable JSON + JOIN program.",
        "JSON_SEAL_PROG": "ARM JSON/SEAL_PROG: sealed JSON keys AND values + JOIN over seals.",
        "JSON_SEAL_NL": "ARM JSON/SEAL_NL: sealed JSON + sealed NL (no program).",
        "JSON_SEAL_BOTH": "ARM JSON/SEAL_BOTH: sealed JSON + sealed NL + JOIN program. Execute JOIN; ignore unreadability of QUESTION.",
        "VAULT_MILD": "ARM VAULT_MILD: readable keys (company, hq_city), sealed entity values, JOIN named in English.",
        "VAULT_STRICT_PROG": "ARM VAULT_STRICT_PROG: sealed keys AND values + JOIN over seals.",
        "VAULT_STRICT_NL": "ARM VAULT_STRICT_NL: sealed keys+values + sealed NL.",
        "VAULT_STRICT_BOTH": "ARM VAULT_STRICT_BOTH: sealed keys+values + sealed NL + JOIN program. Execute JOIN; ignore unreadability of QUESTION.",
    }
    for arm, items in buckets.items():
        d = RUNS / f"{arm}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        fmt = "plain" if arm.endswith("PLAIN_PROG") else "sealed"
        p = d / "BATCH.txt"
        p.write_text(pack(fmt, headers[arm], items))
        paths[arm] = str(p)

    harness = {
        "n": N,
        "seed": SEED,
        "suite": "domain_formats",
        "paths": paths,
        "cases": cases,
        "sealrouter_ceiling": f"{N}/{N}",
        "what_is_sealed": {
            "TABLE_PLAIN_PROG": "nothing",
            "TABLE_SEAL_PROG": "headers + all cells",
            "TABLE_SEAL_NL": "headers + cells + question tokens",
            "TABLE_SEAL_BOTH": "headers + cells + question tokens + JOIN program",
            "JSON_PLAIN_PROG": "nothing",
            "JSON_SEAL_PROG": "object keys + values",
            "JSON_SEAL_NL": "keys + values + question tokens",
            "JSON_SEAL_BOTH": "keys + values + question tokens + JOIN program",
            "VAULT_MILD": "entity values only; keys readable",
            "VAULT_STRICT_PROG": "keys + values",
            "VAULT_STRICT_NL": "keys + values + question tokens",
            "VAULT_STRICT_BOTH": "keys + values + question tokens + JOIN program",
        },
        "what_is_asked": "2-hop person→company→hq_city",
        "what_is_checked": "exact plaintext HQ (PLAIN) or HMAC seal of HQ (sealed arms)",
        "claim": (
            "Dissociation transfers across surface formats: PLAIN_PROG≈SEAL_PROG≫SEAL_NL "
            "on tables and JSON; SEAL_BOTH (sealed NL + PROG) tests whether PROG restores "
            "when the English question is also sealed; VAULT_MILD is the milder industrial pattern."
        ),
    }
    out = RESULTS / "domain_formats_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": N, "arms": list(paths)}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    build()
