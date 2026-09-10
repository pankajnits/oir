#!/usr/bin/env python3
"""
Paired renaming σ/σ′ SEAL_PROG builder (restores missing packaging).

Same CEO→HQ sample as ceiling_three_arm (SEED=20260728, N=12);
two independent HMAC keys. Rebuilds runs/rename_equivariance/ + harness JSON.
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
RUNS = ROOT / "runs" / "rename_equivariance"
SEED = 20260728
N = 12
KEYS = {
    "SIGMA": b"oir-rename-sigma-v1",
    "SIGMA_PRIME": b"oir-rename-sigma-prime-v1",
}


def pack_sealed(items, header: str) -> str:
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
    RUNS.mkdir(parents=True, exist_ok=True)

    cases = []
    arms = {}

    for arm, key in KEYS.items():
        sealer = EntitySeal(key)
        items = []
        for i, row in enumerate(recs):
            person, hq = row["person"], row["hq"]
            edges = ceo_hq_edges(row)
            sealed_triples = [sealer.triple(*e) for e in edges]
            sealed_ctx = SealRouter(sealed_triples).render()
            outs = SealRouter(sealed_triples).path(
                sealer.atom(person),
                [sealer.atom("works_at"), sealer.atom("headquartered_in")],
            )
            assert list(dict.fromkeys(outs)) == [sealer.atom(hq)], (outs, hq)

            prog = path_program(person, ("works_at", "headquartered_in"), hq).seal(sealer)
            prog.meta["start"] = sealer.atom(person)
            prog.meta["rels"] = [
                sealer.atom("works_at"),
                sealer.atom("headquartered_in"),
            ]
            cid = f"RENAME_{arm}_{i}"
            items.append((cid, prog.body, sealed_ctx))
            cases.append(
                {
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "person": person,
                    "hq": hq,
                    "gold_seal": sealer.atom(hq),
                }
            )
        out_dir = RUNS / f"{arm}_ONLY"
        out_dir.mkdir(parents=True, exist_ok=True)
        prompt = pack_sealed(
            items,
            f"ARM {arm}: sealed PATH over CEO→HQ. Follow PATH; emit final sealed atom.",
        )
        (out_dir / "prompt.txt").write_text(prompt)
        arms[arm] = {"path": str(out_dir / "prompt.txt"), "n": N}

    harness = {
        "claim": "Renaming-equivariant SEAL_PROG under independent HMAC keys σ/σ′.",
        "seed": SEED,
        "n_per_key": N,
        "keys": {k: v.decode() for k, v in KEYS.items()},
        "cases": cases,
        "arms": arms,
        "protocol": "batch MUT; isolation; gold stashed",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "rename_equivariance_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    # golds must differ pairwise
    for i in range(N):
        a = next(c for c in cases if c["arm"] == "SIGMA" and c["i"] == i)
        b = next(c for c in cases if c["arm"] == "SIGMA_PRIME" and c["i"] == i)
        assert a["gold_seal"] != b["gold_seal"], i
    print(json.dumps({"n": N * 2, "arms": list(arms), "wrote": str(out)}, indent=2))


if __name__ == "__main__":
    build()
