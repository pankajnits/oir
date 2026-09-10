#!/usr/bin/env python3
"""Expanded three-arm ceiling (N=24). Does NOT overwrite locked n=12 harness."""
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
RUNS = ROOT / "runs" / "ceiling_three_arm_n24"
KEY = b"oir-ceiling-three-arm-v1-n24"
SEED = 20260805
N = 24


def pack_plain(items, header):
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only.",
        "Format: ANSWER_PLAIN[<id>]: <city_or_UNKNOWN>",
        "",
        header,
        "",
    ]
    for cid, body, ctx in items:
        lines.append(f"##### ID {cid} #####\n{body}\n\nCONTEXT:\n{ctx}\n")
    return "\n".join(lines)


def pack_sealed(items, header):
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>",
        "",
        header,
        "",
    ]
    for cid, body, ctx in items:
        lines.append(f"##### ID {cid} #####\n{body}\n\nCONTEXT:\n{ctx}\n")
    return "\n".join(lines)


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    sealer = EntitySeal(KEY)

    plain_items, seal_prog_items, seal_nl_items, cases = [], [], [], []

    for i, row in enumerate(recs):
        person, hq, company = row["person"], row["hq"], row["company"]
        edges = ceo_hq_edges(row)
        plain_ctx = SealRouter(edges).render()
        sealed_triples = [sealer.triple(*e) for e in edges]
        sealed_ctx = SealRouter(sealed_triples).render()

        outs = SealRouter(sealed_triples).path(
            sealer.atom(person),
            [sealer.atom("works_at"), sealer.atom("headquartered_in")],
        )
        assert list(dict.fromkeys(outs)) == [sealer.atom(hq)], (outs, hq)

        prog_plain = path_program(person, ("works_at", "headquartered_in"), hq)
        prog_sealed = prog_plain.seal(sealer)
        prog_sealed.meta["start"] = sealer.atom(person)
        prog_sealed.meta["rels"] = [
            sealer.atom("works_at"),
            sealer.atom("headquartered_in"),
        ]

        cid_a, cid_b, cid_c = f"CEIL24_PLAIN_{i}", f"CEIL24_SEALPROG_{i}", f"CEIL24_SEALNL_{i}"
        plain_items.append((cid_a, prog_plain.body, plain_ctx))
        seal_prog_items.append((cid_b, prog_sealed.body, sealed_ctx))
        q = (
            f"Where is the headquarters of the company that "
            f"{person.replace('_', ' ')} works for?"
        )
        seal_nl_items.append((cid_c, f"QUESTION:\n{sealer.text(q)}", sealed_ctx))
        cases.append(
            {
                "i": i,
                "person": person,
                "company": company,
                "hq": hq,
                "id_plain": cid_a,
                "id_sealprog": cid_b,
                "id_sealnl": cid_c,
                "expect_plain": hq,
                "expect_seal": sealer.atom(hq),
                "company_seal": sealer.atom(company),
            }
        )

    RUNS.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, items, packer, header in [
        ("PLAIN_PROG", plain_items, pack_plain, "ARM A: plaintext PATH binder (language-readable symbols)."),
        ("SEAL_PROG", seal_prog_items, pack_sealed, "ARM B: same PATH binder with opaque sealed atoms."),
        ("SEAL_NL", seal_nl_items, pack_sealed, "ARM C: sealed free NL — no program (negative)."),
    ]:
        d = RUNS / f"{name}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(packer(items, header))
        paths[name] = str(p)

    harness = {
        "n": N,
        "seed": SEED,
        "paths": paths,
        "cases": cases,
        "suite": "ceiling_three_arm_n24",
        "claim": "Expanded N=24 three-arm; does not replace locked n=12.",
        "sealrouter_ceiling": f"{N}/{N}",
    }
    out = RESULTS / "ceiling_three_arm_n24_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": N, "paths": paths, "harness": str(out)}, indent=2))


if __name__ == "__main__":
    build()
