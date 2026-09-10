#!/usr/bin/env python3
"""Hop-4 elicitation: do 2-hop demos transfer TWO extra hops?

CYCLE: 2-hop demos (R,S); 4-hop quiz (R,S,R,S) — recycle demo rels.
DEMO_0: no demos on the same 4-hop family.
PATH: gold program ceiling.

Isolation required for CYCLE/DEMO_0. Not G-Rev1.
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
RUNS = ROOT / "runs" / "hop4"
KEY = b"oir-hop4-v1"
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


def chain(rng: random.Random, hop: int, r1: str, r2: str, tag: str) -> dict:
    rels = ([r1, r2] * ((hop + 1) // 2))[:hop]
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
    return {
        "start": nodes[0],
        "end": nodes[-1],
        "early2": nodes[2] if hop >= 2 else nodes[-1],
        "early3": nodes[3] if hop >= 3 else nodes[-1],
        "rels": list(rels),
        "edges": edges,
        "hop": hop,
    }


def seal_row(row, sealer: EntitySeal):
    sealed = [sealer.triple(*e) for e in row["edges"]]
    ctx = SealRouter(sealed).render()
    start, gold = sealer.atom(row["start"]), sealer.atom(row["end"])
    outs = SealRouter(sealed).path(start, [sealer.atom(r) for r in row["rels"]])
    assert list(dict.fromkeys(outs)) == [gold], (outs, gold)
    return start, gold, ctx, sealed


def demo_block(j, row, sealer):
    s, g, ctx, _ = seal_row(row, sealer)
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

    r1, r2 = "h4_R", "h4_S"
    demos = [chain(rng, 2, r1, r2, f"D{i}") for i in range(K)]
    quizzes = [chain(rng, 4, r1, r2, f"Q{i}") for i in range(N)]
    blocks = [demo_block(j, demos[j], sealer) for j in range(K)]

    arms, cases = {}, []

    def add_iso(arm, header, preamble):
        ids, paths = [], []
        for i, row in enumerate(quizzes):
            cid = f"H4_{arm}_{i}"
            ids.append(cid)
            s, g, ctx, _ = seal_row(row, sealer)
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
                    "early2": sealer.atom(row["early2"]),
                    "early3": sealer.atom(row["early3"]),
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
        "CYCLE",
        "ARM CYCLE: 4 sealed 2-hop demos (R,S); 4-hop quiz (R,S,R,S). One quiz.",
        demo_pre,
    )
    add_iso(
        "DEMO_0",
        "ARM DEMO_0: no demos; 4-hop cycle quiz. One quiz.",
        "No demos. No path. No relation names.\nFrom START, output the sealed answer atom using only CONTEXT.\n\n",
    )

    ids, chunks = [], ["Follow PATH over sealed CONTEXT. Output final sealed atom only.\n\n"]
    for i, row in enumerate(quizzes):
        cid = f"H4_PATH_{i}"
        ids.append(cid)
        _, g, ctx, _ = seal_row(row, sealer)
        prog = path_program(row["start"], tuple(row["rels"]), row["end"]).seal(sealer)
        chunks.append(f"##### ID {cid} #####\n{prog.body}\n\nCONTEXT:\n{ctx}\n")
        cases.append(
            {
                "arm": "PATH",
                "i": i,
                "id": cid,
                "gold": g,
                "early2": sealer.atom(row["early2"]),
                "early3": sealer.atom(row["early3"]),
                "iso": False,
            }
        )
    bp = RUNS / "PATH_BATCH" / "BATCH.txt"
    write(bp, "ARM PATH: gold PATH ceiling on 4-hop cycle. Answer EVERY ID.", "\n".join(chunks))
    arms["PATH"] = {"n": len(ids), "ids": ids, "batch": str(bp), "iso": False}

    out = RESULTS / "hop4_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "hop4",
                "seed": SEED,
                "arms": arms,
                "cases": cases,
                "nonclaim": "2-hop demos → 4-hop is elicitation, not G-Rev1. CYCLE/DEMO_0 isolated.",
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "iso": sum(1 for c in cases if c["iso"]), "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
