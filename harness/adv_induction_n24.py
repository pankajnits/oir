#!/usr/bin/env python3
"""Expanded adversarial traps N=24. Does NOT overwrite locked n=6 harness."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program
from adv_induction import demo_block, make_demo_chain, make_trap_quiz, seal_and_check

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "adv_induction_n24"
KEY = b"oir-adv-induction-n24-v1"
SEED = 20260813
N_QUIZ = 24
N_DEMO = 4


def pack_batch(header: str, items: list[tuple[str, str]]) -> str:
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. Do not open other files.",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>",
        "Answer EVERY ID. If ambiguous, UNKNOWN.",
        "",
        header,
        "",
    ]
    for cid, body in items:
        lines.append(f"##### ID {cid} #####\n{body}\n")
    return "\n".join(lines)


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    RUNS.mkdir(parents=True, exist_ok=True)

    rels_a = ["n24A_r1", "n24A_r2"]
    rels_b = ["n24B_r1", "n24B_r2"]
    trap_rels = ["n24TRAP_r1", "n24TRAP_r2"]
    trap_cross = ["n24Ctrap_r1", "n24Ctrap_r2"]

    demos_a = [make_demo_chain(rng, rels_a, f"N24DA{i}") for i in range(N_DEMO)]
    blocks_a = [
        demo_block(j, d["start"], d["end"], d["edges"], d["rels"], sealer)
        for j, d in enumerate(demos_a)
    ]
    demo_preamble = (
        "Learn the mapping from DEMOs (same encoding).\n"
        "Answer each QUIZ the same way. No English relation names. No PATH.\n"
        "If ambiguous, UNKNOWN.\n\n"
        + "\n\n".join(blocks_a)
        + "\n\n--- QUIZZES ---\n"
    )

    cases = []
    arms = {}

    def emit_trap(arm_name: str, gold_rels, trap_r, label: str):
        items = []
        ids = []
        for i in range(N_QUIZ):
            row = make_trap_quiz(rng, gold_rels, trap_r, f"{arm_name}{i}")
            cid = f"ADV24_{arm_name}_{i}"
            ids.append(cid)
            start, gold, ctx = seal_and_check(
                row["edges"], row["start"], row["end"], row["rels"], sealer
            )
            t_out = SealRouter([sealer.triple(*e) for e in row["edges"]]).path(
                start, [sealer.atom(r) for r in row["trap_rels"]]
            )
            trap = sealer.atom(row["trap_end"])
            assert trap in t_out
            body = f"START {start}\nCONTEXT:\n{ctx}\n"
            items.append((cid, body))
            cases.append(
                {
                    "arm": arm_name,
                    "i": i,
                    "id": cid,
                    "gold": gold,
                    "trap": trap,
                }
            )
        d = RUNS / f"{arm_name}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack_batch(f"ARM {arm_name}: {label}\n{demo_preamble}", items))
        arms[arm_name] = {"label": label, "ids": ids, "path": str(p)}

    emit_trap(
        "SAME_TRAP",
        rels_a,
        trap_rels,
        "demos schemaA; quiz dual-path; gold uses schemaA seals (asymmetric noise on gold mid)",
    )
    emit_trap(
        "CROSS_TRAP",
        rels_b,
        trap_cross,
        "demos schemaA; quiz dual-path; gold uses NOVEL seals",
    )

    # PATH ceiling on SAME_TRAP gold graphs (rebuild same seed quizzes)
    rng_path = random.Random(SEED)
    # consume the same demo draws then SAME quizzes
    for _ in range(N_DEMO):
        make_demo_chain(rng_path, rels_a, "dummy")
    path_items, path_ids = [], []
    for i in range(N_QUIZ):
        row = make_trap_quiz(rng_path, rels_a, trap_rels, f"SAME_TRAP{i}")
        cid = f"ADV24_PATH_TRAP_{i}"
        path_ids.append(cid)
        prog = path_program(row["start"], tuple(row["rels"]), row["end"]).seal(sealer)
        _, gold, ctx = seal_and_check(
            row["edges"], row["start"], row["end"], row["rels"], sealer
        )
        body = f"{prog.body}\n\nCONTEXT:\n{ctx}\n"
        path_items.append((cid, body))
        cases.append({"arm": "PATH_TRAP", "i": i, "id": cid, "gold": gold, "trap": None})
    d = RUNS / "PATH_TRAP_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "BATCH.txt"
    p.write_text(
        pack_batch(
            "ARM PATH_TRAP: follow PATH over sealed CONTEXT; return final sealed atom.",
            path_items,
        )
    )
    arms["PATH_TRAP"] = {
        "label": "PATH ceiling on dual-path graphs",
        "ids": path_ids,
        "path": str(p),
    }

    harness = {
        "n": N_QUIZ,
        "seed": SEED,
        "suite": "adv_induction_n24",
        "claim": "n=24 SAME≫CROSS under asymmetric traps; PATH ceiling on same graphs.",
        "arms": arms,
        "cases": cases,
        "note": "Does not replace locked n=6 adv_induction_harness.json",
    }
    out = RESULTS / "adv_induction_n24_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": N_QUIZ, "arms": {k: v["path"] for k, v in arms.items()}}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    build()
