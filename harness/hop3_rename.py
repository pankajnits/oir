#!/usr/bin/env python3
"""Demo renaming-equivariance: SAME_BALANCED hop-3 under HMAC key σ′.

PATH is already σ/σ′-equivariant. This asks whether *demo elicitation* is too.
Same seed/graphs as hop3_bal SAME; different key; golds must all differ.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter
from hop3_bal import N, K, SEED, demo_2hop, trap_3hop_balanced, demo_block, seal_path, write  # noqa: E402

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "hop3_rename"
KEY = b"oir-hop3-bal-sigma-prime"


def build():
    src = json.loads((RESULTS / "hop3_bal_harness.json").read_text())
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    r1, r2 = "h3b_R", "h3b_S"
    gold_rels = [r1, r2, r1]
    trap_rels = ["h3b_U", "h3b_V", "h3b_U"]
    demos = [demo_2hop(rng, r1, r2, f"D{i}") for i in range(K)]
    blocks = [demo_block(j, demos[j], sealer) for j in range(K)]
    quiz_same = [trap_3hop_balanced(rng, gold_rels, trap_rels, f"QS{i}") for i in range(N)]

    demo_pre = (
        "Learn the mapping from DEMOs (same encoding, novel node seals).\n"
        "Answer the QUIZ the same way. No English relation names. No PATH.\n\n"
        + "\n\n".join(blocks)
        + "\n\n--- QUIZ ---\n"
    )
    header = (
        "ARM SAME_BALANCED σ′: 4 sealed 2-hop demos (R,S); 3-hop quiz gold (R,S,R) "
        "AND a novel trap cycle; symmetric noise. One quiz. New encoding."
    )
    cases, ids, paths = [], [], []
    differ = []
    old_golds = {c["i"]: c["gold"] for c in src["cases"] if c["arm"] == "SAME_BALANCED"}
    for i, row in enumerate(quiz_same):
        cid = f"H3R_SAME_{i}"
        ids.append(cid)
        s, g, ctx, sealed = seal_path(row["edges"], row["start"], row["end"], row["rels"], sealer)
        trap = sealer.atom(row["trap_end"])
        t_out = SealRouter(sealed).path(s, [sealer.atom(r) for r in row["trap_rels"]])
        assert list(dict.fromkeys(t_out)) == [trap]
        q = f"##### ID {cid} #####\nSTART {s}\nCONTEXT:\n{ctx}\n"
        p = RUNS / "SAME" / f"item_{i}" / "prompt.txt"
        write(p, header, demo_pre + q)
        paths.append(str(p))
        old = old_golds[i]
        differ.append(g != old)
        cases.append(
            {
                "arm": "SAME_RENAME",
                "i": i,
                "id": cid,
                "gold": g,
                "gold_sigma": old,
                "trap": trap,
                "early": sealer.atom(row["early"]),
                "iso": True,
                "path": str(p),
            }
        )
    out = {
        "n": N,
        "suite": "hop3_rename",
        "seed": SEED,
        "golds_all_differ": all(differ) and len(differ) == N,
        "arms": {"SAME_RENAME": {"n": N, "ids": ids, "item_paths": paths, "iso": True}},
        "cases": cases,
        "nonclaim": "σ′ elicitation. Not G-Rev1. Golds must differ from hop3_bal SAME.",
    }
    path = RESULTS / "hop3_rename_harness.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps({"golds_all_differ": out["golds_all_differ"], "n": N, "out": str(path)}, indent=2))


if __name__ == "__main__":
    build()
