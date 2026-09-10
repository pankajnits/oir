#!/usr/bin/env python3
"""Fully sealed question + sealed JSON + PROG (product restore).

Same generator as grev1_noprog. English Q is HMAC'd token-wise (function words too);
START token is not re-hashed. JOIN names sealed keys.

Not G-Rev1. Seals ≠ confidentiality.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal
from oir.adapters import load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "grev1_fullq_prog"
KEY = b"oir-grev1-noprog-v1"
SEED = 20260814
N = 6
COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]
KEYS = ("employees", "orgs", "id", "employer", "hq", "city", "country")
ATOM = re.compile(r"[A-Za-z0-9_.\-]+")


def country_of(hq: str) -> str:
    return COUNTRIES[sum(map(ord, hq)) % len(COUNTRIES)]


def nest(city_k, country_k, city_v, country_v, rng):
    items = list({city_k: city_v, country_k: country_v}.items())
    rng.shuffle(items)
    return dict(items)


def seal_question(q: str, sealer: EntitySeal, protect: set[str]) -> str:
    out = []
    for p in re.findall(r"[A-Za-z0-9_.\-]+|[^A-Za-z0-9_.\-]+", q):
        if p in protect:
            out.append(p)
        elif ATOM.fullmatch(p):
            out.append(sealer.atom(p))
        else:
            out.append(p)
    return "".join(out)


def pack(header: str, body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[<id>]: <token_or_UNKNOWN>\n"
        "If more than one reading is possible, output UNKNOWN.\n\n"
        f"{header}\n\n{body}\n"
    )


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    pool = [r for r in graph.records if r not in recs]
    sealer = EntitySeal(KEY)
    k = {name: sealer.atom(name) for name in KEYS}

    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    cases = []
    for i, row in enumerate(recs):
        person, company, hq = row["person"], row["company"], row["hq"]
        country = country_of(hq)
        others = rng.sample(pool, 2)
        pS, cS, hS, nS = (sealer.atom(x) for x in (person, company, hq, country))

        employees = [{k["id"]: pS, k["employer"]: cS}]
        orgs = [{k["id"]: cS, k["hq"]: nest(k["city"], k["country"], hS, nS, rng)}]
        for d in others:
            dc = country_of(d["hq"])
            employees.append({k["id"]: sealer.atom(d["person"]), k["employer"]: sealer.atom(d["company"])})
            orgs.append(
                {
                    k["id"]: sealer.atom(d["company"]),
                    k["hq"]: nest(
                        k["city"], k["country"], sealer.atom(d["hq"]), sealer.atom(dc), rng
                    ),
                }
            )
        rng.shuffle(employees)
        rng.shuffle(orgs)
        ctx = json.dumps({k["employees"]: employees, k["orgs"]: orgs}, indent=2)

        plain_q = f"What is the country of {person.replace('_', ' ')}?"
        layer_q = f"What is the country of {pS}?"
        sealed_q = seal_question(layer_q, sealer, {pS})
        english_in_q = bool(re.search(r"\b(What|country|David|the)\b", sealed_q))

        prog = (
            f"JOIN_QUERY\nSTART {pS}\n"
            f"In array {k['employees']}, match {k['id']} = START, take {k['employer']}.\n"
            f"In array {k['orgs']}, match {k['id']} = that employer, take {k['hq']}.{k['country']}.\n"
            f"Return that atom."
        )
        cid = f"GREV1_FULLQ_PROG_{i}"
        body = (
            f"##### ID {cid} #####\n"
            f"QUESTION (fully token-HMAC'd by the layer; START left as a sealed id):\n"
            f"{sealed_q}\n\n{prog}\n\nCONTEXT:\n{ctx}\n"
        )
        path = RUNS / "FULLQ_PROG" / f"item_{i}" / "prompt.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            pack(
                "ARM FULLQ_PROG: question words HMAC-sealed; JSON keys and values sealed; "
                "JOIN names sealed keys. No plaintext names. One quiz.",
                body,
            )
        )
        cases.append(
            {
                "arm": "FULLQ_PROG",
                "i": i,
                "id": cid,
                "gold": nS,
                "trap": hS,
                "iso": True,
                "path": str(path),
                "plain_q": plain_q,
                "sealed_q": sealed_q,
                "english_in_sealed_q": english_in_q,
                "plain_country": country,
            }
        )

    harness = {
        "n": N,
        "suite": "grev1_fullq_prog",
        "seed": SEED,
        "nonclaim": "PROG given. Not G-Rev1. Not confidentiality. English MUT wrapper is protocol, not the app question.",
        "cases": cases,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "grev1_fullq_prog_harness.json").write_text(json.dumps(harness, indent=2, ensure_ascii=False))
    print(json.dumps({
        "n": N,
        "english_in_q": sum(1 for c in cases if c["english_in_sealed_q"]),
        "sample_q": cases[0]["sealed_q"],
        "plain_q": cases[0]["plain_q"],
    }, indent=2))


if __name__ == "__main__":
    build()
