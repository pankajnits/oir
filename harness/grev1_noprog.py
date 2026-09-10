#!/usr/bin/env python3
"""G-Rev1 pressure: sealed vault, no PROG, no legend.

JSON_KEY_NOLEG still leaked English 'country' (does not HMAC-match keys).
This suite seals the question too.

  QKEY  — Q contains σ(country), which equals the JSON key σ(country).
          Start is a sealed token (layer-bound). No JOIN text.
          Tests opaque query–key unification + walk. Still names the sink field.
  NONE  — Q is only START. City vs country both nested. True G-Rev1:
          no plan, no lexicon. Should be UNKNOWN if honest.

Isolation, n=6. Not a G-Rev1 solve if QKEY hits; NONE is the gate.
Seals ≠ confidentiality.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal
from oir.adapters import load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "grev1_noprog"
KEY = b"oir-grev1-noprog-v1"
SEED = 20260814
N = 6
COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]
KEYS = ("employees", "orgs", "id", "employer", "hq", "city", "country")


def country_of(hq: str) -> str:
    return COUNTRIES[sum(map(ord, hq)) % len(COUNTRIES)]


def pack(header: str, body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[<id>]: <token_or_UNKNOWN>\n"
        "If more than one reading is possible, output UNKNOWN.\n\n"
        f"{header}\n\n{body}\n"
    )


def nest(city_k, country_k, city_v, country_v, rng):
    d = {city_k: city_v, country_k: country_v}
    items = list(d.items())
    rng.shuffle(items)
    return dict(items)


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
                        k["city"],
                        k["country"],
                        sealer.atom(d["hq"]),
                        sealer.atom(dc),
                        rng,
                    ),
                }
            )
        rng.shuffle(employees)
        rng.shuffle(orgs)
        ctx = json.dumps({k["employees"]: employees, k["orgs"]: orgs}, indent=2)

        cid_q = f"GREV1_QKEY_{i}"
        cid_n = f"GREV1_NONE_{i}"
        body_q = (
            f"##### ID {cid_q} #####\n"
            f"QUESTION:\nWhat is {k['country']} of {pS}?\n\n"
            f"CONTEXT:\n{ctx}\n"
        )
        body_n = (
            f"##### ID {cid_n} #####\n"
            f"QUESTION:\nAnswer for {pS}. Return one atom.\n\n"
            f"CONTEXT:\n{ctx}\n"
        )
        pq = RUNS / "QKEY" / f"item_{i}" / "prompt.txt"
        pn = RUNS / "NONE" / f"item_{i}" / "prompt.txt"
        pq.parent.mkdir(parents=True, exist_ok=True)
        pn.parent.mkdir(parents=True, exist_ok=True)
        pq.write_text(
            pack(
                "ARM QKEY: keys and values sealed. Question uses the same HMAC as the JSON key. "
                "No legend. No JOIN/PROG. One quiz.",
                body_q,
            )
        )
        pn.write_text(
            pack(
                "ARM NONE: keys and values sealed. Question is only START. "
                "No legend. No JOIN/PROG. No field name. One quiz.",
                body_n,
            )
        )
        extra = {
            "iso": True,
            "trap": hS,
            "start": pS,
            "k_country": k["country"],
            "plain_person": person,
            "plain_country": country,
        }
        cases.append({"arm": "QKEY", "i": i, "id": cid_q, "gold": nS, "path": str(pq), **extra})
        cases.append({"arm": "NONE", "i": i, "id": cid_n, "gold": nS, "path": str(pn), **extra})

    harness = {
        "n": N,
        "suite": "grev1_noprog",
        "seed": SEED,
        "nonclaim": (
            "QKEY still names the sink as a sealed atom (query–key unification). "
            "NONE is the G-Rev1 gate: no plan, no lexicon. Not confidentiality."
        ),
        "kmap": k,
        "cases": cases,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "grev1_noprog_harness.json").write_text(json.dumps(harness, indent=2, ensure_ascii=False))
    print(json.dumps({"n": N, "arms": ["QKEY", "NONE"], "out": str(RESULTS / "grev1_noprog_harness.json")}, indent=2))


if __name__ == "__main__":
    build()
