#!/usr/bin/env python3
"""Isolation adversarial traps N=32. Does NOT overwrite locked n=6 or batched n=24."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program
from adv_induction import demo_block, make_demo_chain, make_trap_quiz, seal_and_check, pack
from paths import repo_rel

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "adv_induction_n32_iso"
KEY = b"oir-adv-n32-iso-v1!!"  # 16+ bytes ok; EntitySeal may truncate
SEED = 20260819
N_QUIZ = 32
N_DEMO = 4


def write_item(path: Path, header: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack(header, body))


def build() -> None:
    rng = random.Random(SEED)
    # EntitySeal expects 16-byte key in some paths; pad/truncate
    key = (KEY + b"\0" * 16)[:16]
    sealer = EntitySeal(key)
    RUNS.mkdir(parents=True, exist_ok=True)
    for p in RUNS.rglob("prompt.txt"):
        p.unlink()

    rels_a = ["n32A_r1", "n32A_r2"]
    rels_b = ["n32B_r1", "n32B_r2"]
    trap_shared = ["n32TRAP_r1", "n32TRAP_r2"]
    trap_cross = ["n32Ctrap_r1", "n32Ctrap_r2"]

    demos_a = [make_demo_chain(rng, rels_a, f"N32DA{i}") for i in range(N_DEMO)]
    blocks_a = [
        demo_block(j, d["start"], d["end"], d["edges"], d["rels"], sealer)
        for j, d in enumerate(demos_a)
    ]

    arms: dict = {}
    cases: list = []

    def emit(arm_name: str, quiz_rows: list, label: str, kind: str) -> None:
        paths, ids = [], []
        for i, row in enumerate(quiz_rows):
            cid = f"ADV32_{arm_name}_{i}"
            ids.append(cid)
            start, gold, ctx = seal_and_check(
                row["edges"], row["start"], row["end"], row["rels"], sealer
            )
            t_out = SealRouter([sealer.triple(*e) for e in row["edges"]]).path(
                start, [sealer.atom(r) for r in row["trap_rels"]]
            )
            trap = sealer.atom(row["trap_end"])
            assert trap in t_out
            preamble = (
                "Learn the mapping from DEMOs (same encoding).\n"
                "Answer the QUIZ the same way. No English relation names. No PATH.\n"
                "If ambiguous, UNKNOWN.\n\n"
                + "\n\n".join(blocks_a)
                + "\n\n--- QUIZ ---\n"
            )
            body = preamble + f"##### ID {cid} #####\nSTART {start}\nCONTEXT:\n{ctx}\n"
            path = RUNS / arm_name / f"item_{i}" / "prompt.txt"
            write_item(path, f"ARM {arm_name}: {label}", body)
            paths.append(repo_rel(path))
            cases.append(
                {
                    "arm": arm_name,
                    "kind": kind,
                    "i": i,
                    "id": cid,
                    "gold": gold,
                    "trap": trap,
                }
            )
        arms[arm_name] = {
            "label": label,
            "kind": kind,
            "ids": ids,
            "item_paths": paths,
        }

    emit(
        "SAME_TRAP",
        [make_trap_quiz(rng, rels_a, trap_shared, f"QS{i}") for i in range(N_QUIZ)],
        "demos schemaA; quiz dual-path; gold uses schemaA seals (asymmetric noise)",
        "trap_same",
    )
    emit(
        "CROSS_TRAP",
        [make_trap_quiz(rng, rels_b, trap_cross, f"QC{i}") for i in range(N_QUIZ)],
        "demos schemaA; quiz dual-path; gold uses NOVEL seals (asymmetric)",
        "trap_cross",
    )
    emit(
        "SAME_BALANCED",
        [
            make_trap_quiz(rng, rels_a, trap_shared, f"QSB{i}", balanced=True)
            for i in range(N_QUIZ)
        ],
        "SAME seals; dual-path with SYMMETRIC noise",
        "trap_same_balanced",
    )
    emit(
        "CROSS_BALANCED",
        [
            make_trap_quiz(rng, rels_b, trap_cross, f"QCB{i}", balanced=True)
            for i in range(N_QUIZ)
        ],
        "CROSS novel seals; dual-path with SYMMETRIC noise",
        "trap_cross_balanced",
    )

    # PATH ceiling on SAME_TRAP graphs
    paths, ids = [], []
    quiz_same = [make_trap_quiz(rng, rels_a, trap_shared, f"QP{i}") for i in range(N_QUIZ)]
    # Rebuild with dedicated rng state: use cases already sealed from SAME — redo from seed slice
    rng_path = random.Random(SEED + 7)
    quiz_same = [
        make_trap_quiz(rng_path, rels_a, trap_shared, f"QP{i}") for i in range(N_QUIZ)
    ]
    for i, row in enumerate(quiz_same):
        cid = f"ADV32_PATH_TRAP_{i}"
        ids.append(cid)
        prog = path_program(row["start"], tuple(row["rels"]), row["end"]).seal(sealer)
        _, gold, ctx = seal_and_check(
            row["edges"], row["start"], row["end"], row["rels"], sealer
        )
        body = (
            "Follow PATH over sealed CONTEXT. Output final sealed atom only.\n\n"
            f"##### ID {cid} #####\n{prog.body}\n\nCONTEXT:\n{ctx}\n"
        )
        path = RUNS / "PATH_TRAP" / f"item_{i}" / "prompt.txt"
        write_item(path, "ARM PATH_TRAP: gold PATH on dual-path graph.", body)
        paths.append(repo_rel(path))
        cases.append(
            {
                "arm": "PATH_TRAP",
                "kind": "path",
                "i": i,
                "id": cid,
                "gold": gold,
                "trap": None,
            }
        )
    arms["PATH_TRAP"] = {
        "label": "PATH ceiling on trap graphs",
        "kind": "path",
        "ids": ids,
        "item_paths": paths,
    }

    harness = {
        "claim": (
            "Isolation n=32 adversarial traps: SAME vs CROSS under asymmetric and "
            "balanced noise; PATH ceiling. Multi-model iso MUT."
        ),
        "version": 1,
        "seed": SEED,
        "key_tag": "oir-adv-n32-iso-v1",
        "n_quiz": N_QUIZ,
        "n": N_QUIZ,
        "cases": cases,
        "arms": arms,
        "protocol": "one quiz per file; gold in harness only; isolation MUT",
        "note": "Does not replace locked n=6 adv_induction_harness.json or batched n=24",
        "paper": "paper/ADV_INDUCTION.md",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "adv_induction_n32_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    n = sum(len(a["item_paths"]) for a in arms.values())
    print(json.dumps({"n_prompts": n, "arms": list(arms), "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
