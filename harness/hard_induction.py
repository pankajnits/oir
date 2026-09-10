#!/usr/bin/env python3
"""
Hard Opaque Induction — depth stress + cross-schema transfer (G-Rev1 pressure).

Synthetic sealed chains. No English PATH/legend on DEMO arms.
Protocol: one quiz per file; edge shuffle; demos disjoint from quiz entities;
stash harness gold during MUT.
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
RUNS = ROOT / "runs" / "hard_induction"
KEY = b"oir-hard-induction-v1"
SEED = 20260803
N_QUIZ = 6
N_DEMO_MAX = 4
HOPS = (2, 3, 4)
DEMO_KS = (0, 1, 4)


def pack(header: str, body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def make_chain(
    rng: random.Random,
    hop: int,
    rels: list[str],
    tag: str,
) -> dict:
    """Build a hop-length path + decoy edges. entities are synthetic atoms."""
    assert len(rels) == hop
    nodes = [f"{tag}_n{i}_{rng.randrange(1 << 20)}" for i in range(hop + 1)]
    gold_edges = [(nodes[i], rels[i], nodes[i + 1]) for i in range(hop)]
    # decoys: wrong branches from intermediate nodes
    decoys = []
    for i in range(hop):
        d_rel = f"decoy_rel_{tag}_{i}_{rng.randrange(1 << 12)}"
        d_tail = f"{tag}_decoy_{i}_{rng.randrange(1 << 20)}"
        decoys.append((nodes[i], d_rel, d_tail))
        # reverse-ish distractor
        decoys.append((d_tail, f"meta_{tag}_{i}", nodes[i]))
    edges = gold_edges + decoys
    rng.shuffle(edges)
    return {
        "start": nodes[0],
        "end": nodes[-1],
        "rels": list(rels),
        "edges": edges,
        "hop": hop,
        "tag": tag,
    }


def seal_row(row: dict, sealer: EntitySeal) -> tuple[str, str, str, list]:
    sealed = [sealer.triple(*e) for e in row["edges"]]
    ctx = SealRouter(sealed).render()
    start = sealer.atom(row["start"])
    gold = sealer.atom(row["end"])
    r_seals = [sealer.atom(r) for r in row["rels"]]
    outs = SealRouter(sealed).path(start, r_seals)
    assert list(dict.fromkeys(outs)) == [gold], (outs, gold, row)
    return start, gold, ctx, sealed


def demo_block(j: int, row: dict, sealer: EntitySeal) -> str:
    start, gold, ctx, _ = seal_row(row, sealer)
    return f"DEMO {j}:\nSTART {start}\nCONTEXT:\n{ctx}\nANSWER_SEALED: {gold}"


def quiz_body(cid: str, row: dict, sealer: EntitySeal, with_path: bool) -> str:
    start, gold, ctx, _ = seal_row(row, sealer)
    if with_path:
        prog = path_program(row["start"], tuple(row["rels"]), row["end"]).seal(sealer)
        return f"##### ID {cid} #####\n{prog.body}\n\nCONTEXT:\n{ctx}\n"
    return (
        f"##### ID {cid} #####\n"
        f"START {start}\n"
        f"CONTEXT:\n{ctx}\n"
    )


def write_item(path: Path, header: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack(header, body))


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    RUNS.mkdir(parents=True, exist_ok=True)
    for p in RUNS.rglob("prompt.txt"):
        p.unlink()

    arms_meta: dict = {}
    cases: list = []

    # --- DEPTH suite: fixed relation vocabulary per hop ---
    for hop in HOPS:
        rels = [f"rel_h{hop}_step{i}" for i in range(hop)]
        # pool: demos + quiz
        pool = [
            make_chain(rng, hop, rels, tag=f"H{hop}_{i}")
            for i in range(N_DEMO_MAX + N_QUIZ + 2)
        ]
        demos = pool[:N_DEMO_MAX]
        quiz = pool[N_DEMO_MAX : N_DEMO_MAX + N_QUIZ]
        demo_blocks = [demo_block(j, demos[j], sealer) for j in range(N_DEMO_MAX)]

        for k in DEMO_KS:
            arm = f"H{hop}_DEMO_{k}"
            paths = []
            ids = []
            for i, row in enumerate(quiz):
                cid = f"HI_H{hop}_D{k}_{i}"
                ids.append(cid)
                if k == 0:
                    preamble = (
                        "No demos. No path. No relation names.\n"
                        "From START, output the sealed answer atom using only CONTEXT.\n"
                        "If more than one reading is possible, output UNKNOWN.\n\n"
                    )
                else:
                    preamble = (
                        "Learn the mapping from DEMOs (same encoding, novel seals).\n"
                        "Answer the QUIZ the same way. No English relation names. No PATH.\n\n"
                        + "\n\n".join(demo_blocks[:k])
                        + "\n\n--- QUIZ ---\n"
                    )
                body = preamble + quiz_body(cid, row, sealer, with_path=False)
                path = RUNS / arm / f"item_{i}" / "prompt.txt"
                write_item(
                    path,
                    f"ARM {arm}: hop={hop}; {k} sealed demos; one quiz; no PATH.",
                    body,
                )
                paths.append(str(path))
                if k == 0:
                    cases.append(
                        {
                            "suite": "DEPTH",
                            "hop": hop,
                            "i": i,
                            "id_template": f"HI_H{hop}_D{{k}}_{i}",
                            "gold": sealer.atom(row["end"]),
                            "start": sealer.atom(row["start"]),
                            "rels": row["rels"],
                        }
                    )
            arms_meta[arm] = {
                "suite": "DEPTH",
                "hop": hop,
                "n_demo": k,
                "ids": ids,
                "item_paths": paths,
            }

        # PATH ceiling for this hop
        arm = f"H{hop}_PATH"
        paths = []
        ids = []
        for i, row in enumerate(quiz):
            cid = f"HI_H{hop}_PATH_{i}"
            ids.append(cid)
            body = (
                "Follow PATH over sealed CONTEXT. Output final sealed atom only.\n\n"
                + quiz_body(cid, row, sealer, with_path=True)
            )
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            write_item(path, f"ARM {arm}: gold PATH ceiling hop={hop}.", body)
            paths.append(str(path))
            cases.append(
                {
                    "suite": "DEPTH",
                    "hop": hop,
                    "i": i,
                    "arm": "PATH",
                    "id": cid,
                    "gold": sealer.atom(row["end"]),
                }
            )
        arms_meta[arm] = {
            "suite": "DEPTH",
            "hop": hop,
            "n_demo": 0,
            "ids": ids,
            "item_paths": paths,
            "kind": "PATH",
        }

    # --- CROSS suite: demos on schema A, quiz on schema B (hop=2) ---
    rels_a = ["schemaA_r1", "schemaA_r2"]
    rels_b = ["schemaB_r1", "schemaB_r2"]  # novel sealed relation names
    demos_a = [make_chain(rng, 2, rels_a, tag=f"CA_{i}") for i in range(N_DEMO_MAX)]
    quiz_b = [make_chain(rng, 2, rels_b, tag=f"CB_{i}") for i in range(N_QUIZ)]
    quiz_a = [make_chain(rng, 2, rels_a, tag=f"CAsame_{i}") for i in range(N_QUIZ)]
    blocks_a = [demo_block(j, demos_a[j], sealer) for j in range(N_DEMO_MAX)]

    for arm_name, quiz, label in (
        ("CROSS_DEMO_4", quiz_b, "demos schemaA; quiz schemaB (novel rel seals)"),
        ("SAME_DEMO_4", quiz_a, "demos schemaA; quiz schemaA (control)"),
    ):
        paths = []
        ids = []
        for i, row in enumerate(quiz):
            cid = f"HI_{arm_name}_{i}"
            ids.append(cid)
            preamble = (
                "Learn the mapping from DEMOs (same encoding).\n"
                "Answer the QUIZ the same way. No English relation names. No PATH.\n\n"
                + "\n\n".join(blocks_a)
                + "\n\n--- QUIZ ---\n"
            )
            body = preamble + quiz_body(cid, row, sealer, with_path=False)
            path = RUNS / arm_name / f"item_{i}" / "prompt.txt"
            write_item(path, f"ARM {arm_name}: {label}.", body)
            paths.append(str(path))
            cases.append(
                {
                    "suite": "CROSS",
                    "arm": arm_name,
                    "i": i,
                    "id": cid,
                    "gold": sealer.atom(row["end"]),
                    "quiz_rels": row["rels"],
                    "demo_rels": rels_a,
                }
            )
        arms_meta[arm_name] = {
            "suite": "CROSS",
            "n_demo": 4,
            "ids": ids,
            "item_paths": paths,
            "label": label,
        }

    harness = {
        "claim": (
            "Hard opaque induction: depth stress + cross-schema demo transfer "
            "toward G-Rev1 pressure (elicitation limit)."
        ),
        "version": 1,
        "seed": SEED,
        "key_tag": "oir-hard-induction-v1",
        "n_quiz": N_QUIZ,
        "hops": list(HOPS),
        "demo_ks": list(DEMO_KS),
        "cases": cases,
        "arms": arms_meta,
        "protocol": (
            "synthetic chains; one quiz per file; edge shuffle; "
            "no English PATH/legend on DEMO; CROSS uses novel relation seals"
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "hard_induction_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    n = sum(len(a["item_paths"]) for a in arms_meta.values())
    print(json.dumps({"n_prompts": n, "arms": list(arms_meta)}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    build()
