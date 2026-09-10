#!/usr/bin/env python3
"""Hop-3 dual-path traps with BALANCED noise.

Question: 2-hop demos restored 3-hop unique-sink under an *asymmetric*
trap (gold noisier). Does SAME length-transfer survive when gold and trap
mids have the same noise (neither path cleaner)?

SAME_BALANCED: gold reuses demo rels (R,S,R); trap is a novel 3-hop cycle.
CROSS_BALANCED: demos schema A; gold and trap both novel.
DEMO_0_BALANCED: no demos (floor).
PATH_BALANCED: gold PATH (ceiling).

Isolation required for SAME/CROSS/DEMO_0. Not G-Rev1.
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
RUNS = ROOT / "runs" / "hop3_bal"
KEY = b"oir-hop3-bal-v1"
SEED = 20260814
N = 6
K = 4


def pack(header: str, body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n"
        "If more than one reading is possible, output UNKNOWN.\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def demo_2hop(rng: random.Random, r1: str, r2: str, tag: str) -> dict:
    n0, n1, n2 = f"{tag}_a", f"{tag}_b", f"{tag}_c"
    edges = [
        (n0, r1, n1),
        (n1, r2, n2),
        (n0, f"noise_{tag}_0", f"{tag}_n0"),
        (f"{tag}_n0", f"noise_{tag}_1", n0),
    ]
    rng.shuffle(edges)
    return {"start": n0, "end": n2, "rels": [r1, r2], "edges": edges}


def trap_3hop_balanced(
    rng: random.Random,
    gold_rels: list[str],
    trap_rels: list[str],
    tag: str,
) -> dict:
    """Two 3-hop cycles from START. Symmetric noise on gold AND trap mids."""
    assert len(gold_rels) == 3 and len(trap_rels) == 3
    s = f"{tag}_S"
    g1, g2, ge = f"{tag}_G1", f"{tag}_G2", f"{tag}_GE"
    t1, t2, te = f"{tag}_T1", f"{tag}_T2", f"{tag}_TE"
    edges = [
        (s, gold_rels[0], g1),
        (g1, gold_rels[1], g2),
        (g2, gold_rels[2], ge),
        (s, trap_rels[0], t1),
        (t1, trap_rels[1], t2),
        (t2, trap_rels[2], te),
        (g1, f"noiseG_{tag}_1", f"{tag}_nG1"),
        (f"{tag}_nG1", f"metaG_{tag}_1", g1),
        (g2, f"noiseG_{tag}_2", f"{tag}_nG2"),
        (f"{tag}_nG2", f"metaG_{tag}_2", g2),
        (t1, f"noiseT_{tag}_1", f"{tag}_nT1"),
        (f"{tag}_nT1", f"metaT_{tag}_1", t1),
        (t2, f"noiseT_{tag}_2", f"{tag}_nT2"),
        (f"{tag}_nT2", f"metaT_{tag}_2", t2),
    ]
    rng.shuffle(edges)
    return {
        "start": s,
        "end": ge,
        "trap_end": te,
        "early": g2,
        "rels": list(gold_rels),
        "trap_rels": list(trap_rels),
        "edges": edges,
        "balanced": True,
    }


def seal_path(edges, start, end, rels, sealer: EntitySeal):
    sealed = [sealer.triple(*e) for e in edges]
    ctx = SealRouter(sealed).render()
    s, g = sealer.atom(start), sealer.atom(end)
    outs = SealRouter(sealed).path(s, [sealer.atom(r) for r in rels])
    assert list(dict.fromkeys(outs)) == [g], (outs, g)
    return s, g, ctx, sealed


def demo_block(j, row, sealer):
    s, g, ctx, _ = seal_path(row["edges"], row["start"], row["end"], row["rels"], sealer)
    return f"DEMO {j}:\nSTART {s}\nCONTEXT:\n{ctx}\nANSWER_SEALED: {g}"


def write(path: Path, header: str, body: str):
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

    r1, r2 = "h3b_R", "h3b_S"
    gold_rels = [r1, r2, r1]
    trap_rels = ["h3b_U", "h3b_V", "h3b_U"]
    cross_gold = ["h3b_P", "h3b_Q", "h3b_P"]
    cross_trap = ["h3b_X", "h3b_Y", "h3b_X"]

    demos = [demo_2hop(rng, r1, r2, f"D{i}") for i in range(K)]
    blocks = [demo_block(j, demos[j], sealer) for j in range(K)]
    quiz_same = [trap_3hop_balanced(rng, gold_rels, trap_rels, f"QS{i}") for i in range(N)]
    quiz_cross = [trap_3hop_balanced(rng, cross_gold, cross_trap, f"QC{i}") for i in range(N)]

    arms, cases = {}, []

    def add_iso(arm, header, preamble, quizzes, with_path=False):
        ids, paths = [], []
        for i, row in enumerate(quizzes):
            cid = f"H3B_{arm}_{i}"
            ids.append(cid)
            s, g, ctx, sealed = seal_path(row["edges"], row["start"], row["end"], row["rels"], sealer)
            t_out = SealRouter(sealed).path(s, [sealer.atom(r) for r in row["trap_rels"]])
            trap = sealer.atom(row["trap_end"])
            assert list(dict.fromkeys(t_out)) == [trap], (t_out, trap)
            if with_path:
                prog = path_program(row["start"], tuple(row["rels"]), row["end"]).seal(sealer)
                q = f"##### ID {cid} #####\n{prog.body}\n\nCONTEXT:\n{ctx}\n"
            else:
                q = f"##### ID {cid} #####\nSTART {s}\nCONTEXT:\n{ctx}\n"
            p = RUNS / arm / f"item_{i}" / "prompt.txt"
            write(p, header, preamble + q)
            paths.append(str(p))
            cases.append(
                {
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "gold": g,
                    "trap": trap,
                    "early": sealer.atom(row["early"]),
                    "iso": True,
                    "path": str(p),
                }
            )
        arms[arm] = {"n": len(ids), "ids": ids, "item_paths": paths, "iso": True}

    demo_pre = (
        "Learn the mapping from DEMOs (same encoding, novel node seals).\n"
        "Answer the QUIZ the same way. No English relation names. No PATH.\n\n"
        + "\n\n".join(blocks)
        + "\n\n--- QUIZ ---\n"
    )
    add_iso(
        "SAME_BALANCED",
        "ARM SAME_BALANCED: 4 sealed 2-hop demos (R,S); 3-hop quiz has gold (R,S,R) AND a novel trap cycle; symmetric noise on both paths. One quiz.",
        demo_pre,
        quiz_same,
    )
    add_iso(
        "CROSS_BALANCED",
        "ARM CROSS_BALANCED: 4 sealed 2-hop demos schema A; 3-hop quiz gold and trap are both novel cycles; symmetric noise. One quiz.",
        demo_pre,
        quiz_cross,
    )
    add_iso(
        "DEMO_0_BALANCED",
        "ARM DEMO_0_BALANCED: no demos; two 3-hop cycles from START; symmetric noise. One quiz.",
        "No demos. No path. No relation names.\nFrom START, output the sealed answer atom using only CONTEXT.\n\n",
        quiz_same,
    )

    ids, chunks = [], ["Follow PATH over sealed CONTEXT. Output final sealed atom only.\n\n"]
    for i, row in enumerate(quiz_same):
        cid = f"H3B_PATH_{i}"
        ids.append(cid)
        s, g, ctx, _ = seal_path(row["edges"], row["start"], row["end"], row["rels"], sealer)
        prog = path_program(row["start"], tuple(row["rels"]), row["end"]).seal(sealer)
        chunks.append(f"##### ID {cid} #####\n{prog.body}\n\nCONTEXT:\n{ctx}\n")
        cases.append(
            {
                "arm": "PATH",
                "i": i,
                "id": cid,
                "gold": g,
                "trap": sealer.atom(row["trap_end"]),
                "early": sealer.atom(row["early"]),
                "iso": False,
            }
        )
    bp = RUNS / "PATH_BATCH" / "BATCH.txt"
    write(bp, "ARM PATH: gold PATH ceiling on dual 3-hop balanced graph. Answer EVERY ID.", "\n".join(chunks))
    arms["PATH"] = {"n": len(ids), "ids": ids, "batch": str(bp), "iso": False}

    out = RESULTS / "hop3_bal_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "hop3_bal",
                "seed": SEED,
                "arms": arms,
                "cases": cases,
                "nonclaim": (
                    "Balanced trap (symmetric noise). SAME success is relation-token "
                    "binding, not G-Rev1. DEMO_0 / SAME / CROSS are one quiz per file."
                ),
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "iso": sum(1 for c in cases if c["iso"]), "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
