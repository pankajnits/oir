#!/usr/bin/env python3
"""Isolated LLM MUT on G-Rev2 typed-decoy PATH_TYPED_SINK (n=6).

Question: does a cloud MUT execute the well-posed program under distractors
where type-only fails? GNN/MP is 200/200 on this generator.
Not G-Rev1: PATH + SINK_TYPE given.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from grev2_typed_sink import make_example, parse, typed_sink_router, unique_router  # noqa: E402
from grev2_local_mp import type_only  # noqa: E402

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "grev2_decoy_mut"
SEED = 20260814
N = 6


def pack(body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n"
        "If more than one reading is possible, output UNKNOWN.\n\n"
        "ARM PATH_TYPED_SINK: follow PATH; final node must have the SINK_TYPE edge. One quiz.\n\n"
        f"{body}\n"
    )


def main():
    rng = random.Random(SEED)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)
    cases = []
    paths = []
    ids = []
    for i in range(N):
        raw = make_example(rng, i, hops=2, n_decoy=2, n_false_type=2, tag="mutd")
        ex = parse(raw)
        assert typed_sink_router(ex) == ex["gold"]
        assert type_only(ex) != ex["gold"]
        assert (unique_router(ex) or "") != ex["gold"]
        cid = f"GREV2_DECOY_{i}"
        ids.append(cid)
        p = RUNS / f"item_{i}" / "prompt.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(pack(f"##### ID {cid} #####\n{raw['input']}"))
        paths.append(str(p))
        cases.append({"arm": "DECOY_MUT", "i": i, "id": cid, "gold": ex["gold"], "iso": True, "path": str(p)})
    out = RESULTS / "grev2_decoy_mut_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "grev2_decoy_mut",
                "seed": SEED,
                "arms": {"DECOY_MUT": {"n": N, "ids": ids, "item_paths": paths, "iso": True}},
                "cases": cases,
                "nonclaim": "PATH+SINK_TYPE given. Not G-Rev1. Type-only fails on these items.",
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "out": str(out), "paths": paths}, indent=2))


if __name__ == "__main__":
    main()
