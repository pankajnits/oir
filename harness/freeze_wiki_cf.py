#!/usr/bin/env python3
"""Freeze 2Wiki-CF graphs (counterfactual gold + competing Wikipedia trap).

n=200 unique-path test from validation compositional pool.
No overlap with data/2wiki_compositional_n12.json.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter

SEED = 20260813
KEY = b"oir-wiki-cf-n200-v1"
SRC = ROOT / "data" / "2wiki_compositional_dev.json"
PILOT = ROOT / "data" / "2wiki_compositional_n12.json"
OUT = ROOT / "data" / "wiki_cf_n200.json"
SRC200 = ROOT / "data" / "2wiki_compositional_n200.json"
N = 200


def try_case(i, it, sealer: EntitySeal, rng: random.Random, distractors):
    ev = it["evidences"]
    start, r1, mid = ev[0]
    _, r2, wiki = ev[1]
    if len({start, mid, wiki}) < 3:
        return None
    cf = f"CF_TAIL_{i}_{re.sub(r'[^A-Za-z0-9]+', '', wiki)[:12] or 'X'}"
    trap_rel = f"decoy_link_{i}"
    trap_mid = f"decoy_mid_{i}"
    edges = [
        (start, r1, mid),
        (mid, r2, cf),
        (start, trap_rel, trap_mid),
        (trap_mid, r2, wiki),
    ]
    for d in distractors:
        e0, e1 = tuple(d["evidences"][0]), tuple(d["evidences"][1])
        if e0[0] == start and e0[1] == r1:
            return None
        if e1[0] == mid and e1[1] == r2:
            return None
        edges += [e0, e1]
    rng.shuffle(edges)
    gold_seal = sealer.atom(cf)
    outs = SealRouter([sealer.triple(*e) for e in edges]).path(
        sealer.atom(start), [sealer.atom(r1), sealer.atom(r2)]
    )
    if list(dict.fromkeys(outs)) != [gold_seal]:
        return None
    return {
        "i": i,
        "wiki_id": it["id"],
        "question": it["question"],
        "wiki_answer": wiki,
        "cf_gold": cf,
        "start": start,
        "mid": mid,
        "rels": [r1, r2],
        "edges": [list(e) for e in edges],
        "expect_plain": cf,
        "expect_seal": gold_seal,
        "wiki_seal": sealer.atom(wiki),
        "start_seal": sealer.atom(start),
        "rel_seals": [sealer.atom(r1), sealer.atom(r2)],
        "source_item": it,
    }


def main():
    pool = json.loads(SRC.read_text())["items"]
    ban = {x["id"] for x in json.loads(PILOT.read_text())["items"]}
    sealer = EntitySeal(KEY)
    rng = random.Random(SEED)
    order = list(range(len(pool)))
    rng.shuffle(order)
    cases = []
    for idx in order:
        if len(cases) >= N:
            break
        it = pool[idx]
        if it["id"] in ban:
            continue
        d1 = pool[(idx + 1) % len(pool)]
        d2 = pool[(idx + 2) % len(pool)]
        c = try_case(len(cases), it, sealer, rng, [d1, d2])
        if c is None:
            continue
        cases.append(c)
    if len(cases) < N:
        raise SystemExit(f"only got {len(cases)} unique-path CF cases")
    src_items = [c.pop("source_item") for c in cases]
    SRC200.write_text(
        json.dumps(
            {
                "source": "2WikiMultihopQA validation compositional 2-hop (held-out from n=12 pilot)",
                "license": "Apache-2.0",
                "seed": SEED,
                "n": N,
                "items": src_items,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    OUT.write_text(
        json.dumps(
            {
                "suite": "wiki_cf",
                "n": len(cases),
                "seed": SEED,
                "key_id": "oir-wiki-cf-n200-v1",
                "source": "2WikiMultihopQA validation compositional (Apache-2.0)",
                "pilot_excluded": True,
                "falsifier": "PLAIN_NL == original 2Wiki answer → parametric cheat; gold is CF_TAIL_*",
                "nonclaim": "Not G-Rev1. Unigram relation leak still possible if graph rels stay English.",
                "cases": cases,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(json.dumps({"n": len(cases), "out": str(OUT), "src200": str(SRC200)}, indent=2))


if __name__ == "__main__":
    main()
