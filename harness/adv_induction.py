#!/usr/bin/env python3
"""
Adversarial Opaque Induction — break isomorphic demo transfer (G-Rev1 honesty).

Insight: CROSS=6/6 on isomorphic chains may be shape matching, not opaque composition.
Attack:
  TRAP  — quiz has TWO complete 2-hop paths from START (gold + trap);
          demos teach which relation seals to follow (SAME) or leave novel (CROSS).
  MISMATCH — demos are 2-hop; quiz is 3-hop (blind 2-hop copy fails).

If SAME_TRAP ≫ CROSS_TRAP → demos bind specific sealed relations, not native composition.
If both high → residual shape/heuristic leak; tighten generator.
If MISMATCH fails → elicitation does not invent deeper programs (supports binder limit).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter, path_program

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "adv_induction"
KEY = b"oir-adv-induction-v1"
SEED = 20260803
N_QUIZ = 6
N_DEMO = 4


def pack(header: str, body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def seal_and_check(edges, start, end, rels, sealer: EntitySeal):
    sealed = [sealer.triple(*e) for e in edges]
    ctx = SealRouter(sealed).render()
    s, g = sealer.atom(start), sealer.atom(end)
    outs = SealRouter(sealed).path(s, [sealer.atom(r) for r in rels])
    assert list(dict.fromkeys(outs)) == [g], (outs, g)
    return s, g, ctx


def demo_block(j, start, end, edges, rels, sealer):
    s, g, ctx = seal_and_check(edges, start, end, rels, sealer)
    return f"DEMO {j}:\nSTART {s}\nCONTEXT:\n{ctx}\nANSWER_SEALED: {g}"


def make_demo_chain(rng: random.Random, rels: list[str], tag: str):
    """Clean 2-hop demo (one gold path + light decoys that are NOT full alternate paths)."""
    n0, n1, n2 = f"{tag}_a", f"{tag}_b", f"{tag}_c"
    edges = [
        (n0, rels[0], n1),
        (n1, rels[1], n2),
        (n0, f"noise_{tag}_0", f"{tag}_noise0"),
        (f"{tag}_noise0", f"noise_{tag}_1", n0),
    ]
    rng.shuffle(edges)
    return {"start": n0, "end": n2, "rels": rels, "edges": edges}


def make_trap_quiz(
    rng: random.Random,
    gold_rels: list[str],
    trap_rels: list[str],
    tag: str,
    *,
    balanced: bool = False,
):
    """Two full 2-hop paths from START: gold via gold_rels, trap via trap_rels.

    Default (balanced=False): light noise hangs only off gold mid (trap looks cleaner).
    Balanced: symmetric noise on both mids (or none) — fairer composition probe.
    """
    start = f"{tag}_S"
    mid_g, end_g = f"{tag}_Mg", f"{tag}_Eg"
    mid_t, end_t = f"{tag}_Mt", f"{tag}_Et"
    edges = [
        (start, gold_rels[0], mid_g),
        (mid_g, gold_rels[1], end_g),
        (start, trap_rels[0], mid_t),
        (mid_t, trap_rels[1], end_t),
    ]
    if balanced:
        edges += [
            (mid_g, f"noiseG_{tag}", f"{tag}_nG"),
            (f"{tag}_nG", f"metaG_{tag}", mid_g),
            (mid_t, f"noiseT_{tag}", f"{tag}_nT"),
            (f"{tag}_nT", f"metaT_{tag}", mid_t),
        ]
    else:
        edges += [
            (mid_g, f"noise_{tag}", f"{tag}_n"),
            (f"{tag}_n", f"meta_{tag}", mid_g),
        ]
    rng.shuffle(edges)
    return {
        "start": start,
        "end": end_g,  # gold only
        "trap_end": end_t,
        "rels": gold_rels,
        "trap_rels": trap_rels,
        "edges": edges,
        "balanced": balanced,
    }


def make_mismatch_quiz(rng: random.Random, rels3: list[str], tag: str):
    """3-hop gold path; also a tempting 2-hop decoy from start (wrong)."""
    nodes = [f"{tag}_n{i}" for i in range(4)]
    mid_wrong, end_wrong = f"{tag}_w1", f"{tag}_w2"
    edges = [
        (nodes[0], rels3[0], nodes[1]),
        (nodes[1], rels3[1], nodes[2]),
        (nodes[2], rels3[2], nodes[3]),
        # tempting 2-hop trap
        (nodes[0], f"trap2_{tag}_r0", mid_wrong),
        (mid_wrong, f"trap2_{tag}_r1", end_wrong),
    ]
    rng.shuffle(edges)
    return {
        "start": nodes[0],
        "end": nodes[3],
        "wrong_2hop": end_wrong,
        "rels": rels3,
        "edges": edges,
        "hop": 3,
    }


def write_item(path: Path, header: str, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack(header, body))


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    RUNS.mkdir(parents=True, exist_ok=True)
    for p in RUNS.rglob("prompt.txt"):
        p.unlink()

    rels_a = ["advA_r1", "advA_r2"]
    rels_b = ["advB_r1", "advB_r2"]  # novel for CROSS
    trap_rels_shared = ["advTRAP_r1", "advTRAP_r2"]
    rels3 = ["adv3_r1", "adv3_r2", "adv3_r3"]

    demos_a = [make_demo_chain(rng, rels_a, f"DA{i}") for i in range(N_DEMO)]
    blocks_a = [
        demo_block(j, d["start"], d["end"], d["edges"], d["rels"], sealer)
        for j, d in enumerate(demos_a)
    ]

    arms = {}
    cases = []

    # --- SAME_TRAP: demos A; quiz trap with gold=A seals, trap=other ---
    quiz_same = [
        make_trap_quiz(rng, rels_a, trap_rels_shared, f"QS{i}") for i in range(N_QUIZ)
    ]
    # --- CROSS_TRAP: demos A; quiz gold=B (novel), trap=other novel ---
    quiz_cross = [
        make_trap_quiz(rng, rels_b, [f"advCtrap_r1", f"advCtrap_r2"], f"QC{i}")
        for i in range(N_QUIZ)
    ]
    # --- MISMATCH: demos 2-hop A; quiz 3-hop ---
    quiz_mis = [make_mismatch_quiz(rng, rels3, f"QM{i}") for i in range(N_QUIZ)]
    # demos for mismatch use 2-hop with first two of rels3? Better: demos on A, quiz 3-hop novel
    # Use separate 2-hop demos then 3-hop quiz with novel rels — pure hop invention test
    demos_2 = [make_demo_chain(rng, ["misD_r1", "misD_r2"], f"DM{i}") for i in range(N_DEMO)]
    blocks_2 = [
        demo_block(j, d["start"], d["end"], d["edges"], d["rels"], sealer)
        for j, d in enumerate(demos_2)
    ]

    def emit_demo_arm(arm_name, blocks, quiz_rows, label, kind):
        paths, ids = [], []
        for i, row in enumerate(quiz_rows):
            cid = f"ADV_{arm_name}_{i}"
            ids.append(cid)
            start, gold, ctx = seal_and_check(
                row["edges"], row["start"], row["end"], row["rels"], sealer
            )
            # verify trap also reachable as 2-hop for trap quizzes
            if "trap_end" in row:
                t_out = SealRouter([sealer.triple(*e) for e in row["edges"]]).path(
                    start, [sealer.atom(r) for r in row["trap_rels"]]
                )
                assert sealer.atom(row["trap_end"]) in t_out
            preamble = (
                "Learn the mapping from DEMOs (same encoding).\n"
                "Answer the QUIZ the same way. No English relation names. No PATH.\n"
                "If ambiguous, UNKNOWN.\n\n"
                + "\n\n".join(blocks)
                + "\n\n--- QUIZ ---\n"
            )
            body = preamble + f"##### ID {cid} #####\nSTART {start}\nCONTEXT:\n{ctx}\n"
            path = RUNS / arm_name / f"item_{i}" / "prompt.txt"
            write_item(path, f"ARM {arm_name}: {label}", body)
            paths.append(str(path))
            cases.append(
                {
                    "arm": arm_name,
                    "kind": kind,
                    "i": i,
                    "id": cid,
                    "gold": gold,
                    "trap": sealer.atom(row["trap_end"]) if "trap_end" in row else None,
                    "wrong_2hop": sealer.atom(row["wrong_2hop"])
                    if "wrong_2hop" in row
                    else None,
                }
            )
        arms[arm_name] = {
            "label": label,
            "kind": kind,
            "ids": ids,
            "item_paths": paths,
        }

    emit_demo_arm(
        "SAME_TRAP",
        blocks_a,
        quiz_same,
        "demos schemaA; quiz dual-path; gold uses schemaA seals",
        "trap_same",
    )
    emit_demo_arm(
        "CROSS_TRAP",
        blocks_a,
        quiz_cross,
        "demos schemaA; quiz dual-path; gold uses NOVEL seals (shape match insufficient)",
        "trap_cross",
    )
    emit_demo_arm(
        "HOP_MISMATCH",
        blocks_2,
        quiz_mis,
        "demos 2-hop; quiz 3-hop novel; blind 2-hop copy = wrong_2hop",
        "mismatch",
    )

    # --- Balanced-noise controls (symmetric noise on gold+trap mids) ---
    quiz_same_bal = [
        make_trap_quiz(rng, rels_a, trap_rels_shared, f"QSB{i}", balanced=True)
        for i in range(N_QUIZ)
    ]
    quiz_cross_bal = [
        make_trap_quiz(
            rng, rels_b, [f"advCtrap_r1", f"advCtrap_r2"], f"QCB{i}", balanced=True
        )
        for i in range(N_QUIZ)
    ]
    emit_demo_arm(
        "SAME_BALANCED",
        blocks_a,
        quiz_same_bal,
        "SAME seals; dual-path with SYMMETRIC noise on gold+trap mids",
        "trap_same_balanced",
    )
    emit_demo_arm(
        "CROSS_BALANCED",
        blocks_a,
        quiz_cross_bal,
        "CROSS novel seals; dual-path with SYMMETRIC noise on gold+trap mids",
        "trap_cross_balanced",
    )

    # PATH ceiling on trap_same gold
    paths, ids = [], []
    for i, row in enumerate(quiz_same):
        cid = f"ADV_PATH_TRAP_{i}"
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
        paths.append(str(path))
        cases.append({"arm": "PATH_TRAP", "kind": "path", "i": i, "id": cid, "gold": gold})
    arms["PATH_TRAP"] = {
        "label": "PATH ceiling on trap graphs",
        "kind": "path",
        "ids": ids,
        "item_paths": paths,
    }

    harness = {
        "claim": (
            "Adversarial opaque induction: dual-path traps + hop mismatch to test whether "
            "demo success is isomorphic shape matching vs sealed-relation binding."
        ),
        "version": 1,
        "seed": SEED,
        "key_tag": "oir-adv-induction-v1",
        "n_quiz": N_QUIZ,
        "cases": cases,
        "arms": arms,
        "protocol": "one quiz per file; stash gold; isolation MUT",
        "paper": "paper/PAPER_STATUS.md B1",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "adv_induction_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    n = sum(len(a["item_paths"]) for a in arms.values())
    print(json.dumps({"n_prompts": n, "arms": list(arms)}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    build()
