#!/usr/bin/env python3
"""Hop-mismatch opaque induction (G-Rev1 / G-Inc1 pressure).

Question: do k sealed 2-hop demos teach a composition *procedure* that
generalizes to a 3-hop quiz, or only the demonstrated length?

CYCLE uses only relation seals that appeared in demos (extra hop recycles R).
CROSS uses a novel relation vocabulary on a 3-hop cycle.
DEMO_0 is the no-binder floor on the same 3-hop cycle family.
H3_DEMO_4 is same-depth elicitation (control).
PATH is the gold-program ceiling.

Protocol: CYCLE / DEMO_0 / CROSS are one quiz per file (required: a batch of
3-hop quizzes would become 3-hop demos). PATH and H3_DEMO_4 may be batched.

Not G-Rev1 even if CYCLE saturates — demos remain a binder.
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
RUNS = ROOT / "runs" / "hop_mismatch"
KEY = b"oir-hop-mismatch-v1"
SEED = 20260814
N = 6
K_DEMO = 4


def pack(header: str, body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n"
        "If more than one reading is possible, output UNKNOWN.\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def chain_cycle(rng: random.Random, hop: int, r1: str, r2: str, tag: str) -> dict:
    """hop in {2,3}. hop=2: R,S. hop=3: R,S,R (length extra, no novel rel)."""
    rels = [r1, r2] if hop == 2 else [r1, r2, r1]
    nodes = [f"{tag}_n{i}_{rng.randrange(1 << 20)}" for i in range(hop + 1)]
    gold = [(nodes[i], rels[i], nodes[i + 1]) for i in range(hop)]
    decoys = []
    for i in range(hop):
        d_rel = f"decoy_{tag}_{i}_{rng.randrange(1 << 12)}"
        d_tail = f"{tag}_decoy_{i}_{rng.randrange(1 << 20)}"
        decoys.append((nodes[i], d_rel, d_tail))
        decoys.append((d_tail, f"meta_{tag}_{i}", nodes[i]))
    edges = gold + decoys
    rng.shuffle(edges)
    early = nodes[2] if hop == 3 else nodes[-1]
    return {
        "start": nodes[0],
        "end": nodes[-1],
        "early": early,
        "rels": list(rels),
        "edges": edges,
        "hop": hop,
        "tag": tag,
    }


def seal_row(row: dict, sealer: EntitySeal):
    sealed = [sealer.triple(*e) for e in row["edges"]]
    ctx = SealRouter(sealed).render()
    start = sealer.atom(row["start"])
    gold = sealer.atom(row["end"])
    early = sealer.atom(row["early"])
    r_seals = [sealer.atom(r) for r in row["rels"]]
    outs = SealRouter(sealed).path(start, r_seals)
    assert list(dict.fromkeys(outs)) == [gold], (outs, gold)
    return start, gold, early, ctx


def demo_block(j: int, row: dict, sealer: EntitySeal) -> str:
    start, gold, _, ctx = seal_row(row, sealer)
    return f"DEMO {j}:\nSTART {start}\nCONTEXT:\n{ctx}\nANSWER_SEALED: {gold}"


def quiz_nl(cid: str, row: dict, sealer: EntitySeal) -> str:
    start, _, _, ctx = seal_row(row, sealer)
    return f"##### ID {cid} #####\nSTART {start}\nCONTEXT:\n{ctx}\n"


def quiz_path(cid: str, row: dict, sealer: EntitySeal) -> str:
    _, _, _, ctx = seal_row(row, sealer)
    prog = path_program(row["start"], tuple(row["rels"]), row["end"]).seal(sealer)
    return f"##### ID {cid} #####\n{prog.body}\n\nCONTEXT:\n{ctx}\n"


def write(path: Path, header: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack(header, body))


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
        for p in RUNS.rglob("BATCH.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    r1, r2 = "cycle_R", "cycle_S"
    ua, ub = "cross_U", "cross_V"

    demos_h2 = [chain_cycle(rng, 2, r1, r2, f"D2_{i}") for i in range(K_DEMO)]
    demos_h3 = [chain_cycle(rng, 3, r1, r2, f"D3_{i}") for i in range(K_DEMO)]
    demos_cross = [chain_cycle(rng, 2, ua, ub, f"CXD_{i}") for i in range(K_DEMO)]
    quiz_h3 = [chain_cycle(rng, 3, r1, r2, f"Q3_{i}") for i in range(N)]
    quiz_cross = [chain_cycle(rng, 3, ua, ub, f"CXQ_{i}") for i in range(N)]

    blocks_h2 = [demo_block(j, demos_h2[j], sealer) for j in range(K_DEMO)]
    blocks_h3 = [demo_block(j, demos_h3[j], sealer) for j in range(K_DEMO)]
    blocks_cx = [demo_block(j, demos_cross[j], sealer) for j in range(K_DEMO)]

    arms = {}
    cases = []

    def add_iso(arm: str, header: str, preamble: str, quizzes: list, with_path: bool):
        paths = []
        ids = []
        for i, row in enumerate(quizzes):
            cid = f"HM_{arm}_{i}"
            ids.append(cid)
            body = preamble + (quiz_path(cid, row, sealer) if with_path else quiz_nl(cid, row, sealer))
            p = RUNS / arm / f"item_{i}" / "prompt.txt"
            write(p, header, body)
            paths.append(str(p))
            cases.append(
                {
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "gold": sealer.atom(row["end"]),
                    "early": sealer.atom(row["early"]),
                    "start": sealer.atom(row["start"]),
                    "hop": row["hop"],
                    "path": str(p),
                    "iso": True,
                }
            )
        arms[arm] = {"n": len(ids), "ids": ids, "item_paths": paths, "iso": True}

    add_iso(
        "H3_DEMO_0",
        "ARM H3_DEMO_0: 3-hop cycle quiz; no demos; no PATH.",
        "No demos. No path. No relation names.\n"
        "From START, output the sealed answer atom using only CONTEXT.\n\n",
        quiz_h3,
        False,
    )
    add_iso(
        "H2D_H3Q_CYCLE",
        "ARM H2D_H3Q_CYCLE: 4 sealed 2-hop demos (R,S); 3-hop quiz (R,S,R). One quiz. No PATH.",
        "Learn the mapping from DEMOs (same encoding, novel node seals).\n"
        "Answer the QUIZ the same way. No English relation names. No PATH.\n\n"
        + "\n\n".join(blocks_h2)
        + "\n\n--- QUIZ ---\n",
        quiz_h3,
        False,
    )
    add_iso(
        "H2D_H3Q_CROSS",
        "ARM H2D_H3Q_CROSS: 4 sealed 2-hop demos schema A; 3-hop cycle quiz schema B. One quiz. No PATH.",
        "Learn the mapping from DEMOs (same encoding).\n"
        "Answer the QUIZ the same way. No English relation names. No PATH.\n\n"
        + "\n\n".join(blocks_cx)
        + "\n\n--- QUIZ ---\n",
        quiz_cross,
        False,
    )

    # Batched controls (PATH + same-depth demos)
    def add_batch(arm: str, header: str, preamble: str, quizzes: list, with_path: bool):
        ids = []
        chunks = [preamble]
        for i, row in enumerate(quizzes):
            cid = f"HM_{arm}_{i}"
            ids.append(cid)
            chunks.append(quiz_path(cid, row, sealer) if with_path else quiz_nl(cid, row, sealer))
            cases.append(
                {
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "gold": sealer.atom(row["end"]),
                    "early": sealer.atom(row["early"]),
                    "start": sealer.atom(row["start"]),
                    "hop": row["hop"],
                    "iso": False,
                }
            )
        p = RUNS / f"{arm}_BATCH" / "BATCH.txt"
        write(p, header, "\n".join(chunks))
        arms[arm] = {"n": len(ids), "ids": ids, "batch": str(p), "iso": False}

    add_batch(
        "H3_PATH",
        "ARM H3_PATH: gold PATH ceiling on 3-hop cycle. Answer EVERY ID.",
        "Follow PATH over sealed CONTEXT. Output final sealed atom only.\n\n",
        quiz_h3,
        True,
    )
    add_batch(
        "H3_DEMO_4",
        "ARM H3_DEMO_4: 4 sealed 3-hop demos; 3-hop quizzes (same-depth control). Answer EVERY ID.",
        "Learn the mapping from DEMOs (same encoding).\n"
        "Answer each QUIZ the same way. No PATH.\n\n"
        + "\n\n".join(blocks_h3)
        + "\n\n--- QUIZZES ---\n",
        quiz_h3,
        False,
    )

    out = RESULTS / "hop_mismatch_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "k_demo": K_DEMO,
                "seed": SEED,
                "suite": "hop_mismatch",
                "arms": arms,
                "cases": cases,
                "nonclaim": (
                    "Demos remain a binder. CYCLE success is length transfer, not G-Rev1. "
                    "H3_DEMO_4 and H3_PATH are batched (protocol-scoped). "
                    "DEMO_0 / CYCLE / CROSS are one quiz per file."
                ),
            },
            indent=2,
        )
    )
    iso_n = sum(1 for c in cases if c["iso"])
    print(json.dumps({"n": N, "iso_prompts": iso_n, "arms": {k: v.get("iso") for k, v in arms.items()}, "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
