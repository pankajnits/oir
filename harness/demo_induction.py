#!/usr/bin/env python3
"""
Demo-only induction under opacity (NEXT_MOVE) — v2 protocol.

v1 confound (discarded): batched 8 isomorphic quizzes + English "two-hop"
let DEMO_0 induce the shared relation seals within-prompt → false 8/8.

v2 fixes
--------
  - One QUIZ item per prompt file (kills within-batch schema induction).
  - No English hop/program wording on DEMO arms; demos teach by example only.
  - Per-item edge shuffle (seeded) — not decoy-last position heuristic.
  - DEMO_0 question matches three-arm spirit: START + CONTEXT only; UNKNOWN if ambiguous.
  - LEGEND / PATH remain binder controls (may batch; ceiling already locked).

Arms
----
  DEMO_k (k=0,1,2,4,8): k sealed demos + ONE sealed quiz
  LEGEND: English relation-role legend
  PATH: gold PATH ceiling
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program
from oir.adapters import ceo_hq_edges, load_ceo_hq_graph
from paths import repo_rel

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "demo_induction"
KEY = b"oir-demo-induction-v2"
SEED = 20260729
N_QUIZ = 8
N_DEMO_MAX = 8
KS = (0, 1, 2, 4, 8)


def shuffle_edges(
    edges: list[tuple[str, str, str]], rng: random.Random
) -> list[tuple[str, str, str]]:
    e = list(edges)
    rng.shuffle(e)
    return e


def make_demo_block(j: int, row: dict, sealer: EntitySeal, rng: random.Random) -> str:
    edges = shuffle_edges(ceo_hq_edges(row), rng)
    sealed = [sealer.triple(*e) for e in edges]
    ctx = SealRouter(sealed).render()
    start = sealer.atom(row["person"])
    gold = sealer.atom(row["hq"])
    outs = SealRouter(sealed).path(
        start, [sealer.atom("works_at"), sealer.atom("headquartered_in")]
    )
    assert list(dict.fromkeys(outs)) == [gold]
    return (
        f"DEMO {j}:\n"
        f"START {start}\n"
        f"CONTEXT:\n{ctx}\n"
        f"ANSWER_SEALED: {gold}"
    )


def pack(header: str, body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. "
        "Do not open other files.\n"
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    pool = rng.sample(graph.records, N_QUIZ + N_DEMO_MAX + 4)
    demos = pool[:N_DEMO_MAX]
    quiz = pool[N_DEMO_MAX : N_DEMO_MAX + N_QUIZ]
    sealer = EntitySeal(KEY)

    # Stable demo blocks (own RNG stream so quiz shuffles independent)
    demo_rng = random.Random(SEED + 1)
    demo_blocks = [
        make_demo_block(j, demos[j], sealer, random.Random(demo_rng.randint(0, 2**30)))
        for j in range(N_DEMO_MAX)
    ]

    RUNS.mkdir(parents=True, exist_ok=True)
    # wipe old v1 batch prompts
    for p in RUNS.rglob("prompt.txt"):
        p.unlink()

    cases = []
    arms_meta: dict = {}
    r1, r2 = sealer.atom("works_at"), sealer.atom("headquartered_in")

    # --- DEMO_k: one quiz item per file ---
    for k in KS:
        arm_name = f"DEMO_{k}"
        arm_dir = RUNS / f"{arm_name}_ONLY"
        arm_dir.mkdir(exist_ok=True)
        item_paths = []
        ids = []

        for i, row in enumerate(quiz):
            item_rng = random.Random(SEED + 1000 + k * 100 + i)
            edges = shuffle_edges(ceo_hq_edges(row), item_rng)
            sealed = [sealer.triple(*e) for e in edges]
            ctx = SealRouter(sealed).render()
            start = sealer.atom(row["person"])
            gold = sealer.atom(row["hq"])
            outs = SealRouter(sealed).path(start, [r1, r2])
            assert list(dict.fromkeys(outs)) == [gold]
            cid = f"DI_DEMO{k}_{i}"
            ids.append(cid)

            if k == 0:
                preamble = (
                    "No demos. No path. No relation names.\n"
                    "From START, output the sealed answer atom using only CONTEXT.\n"
                    "If more than one reading is possible, output UNKNOWN.\n\n"
                )
                cases.append(
                    {
                        "i": i,
                        "person": row["person"],
                        "hq": row["hq"],
                        "company": row["company"],
                        "gold": gold,
                        "start": start,
                    }
                )
            else:
                preamble = (
                    "Learn the mapping from DEMOs (same encoding, novel seals).\n"
                    "Then answer the QUIZ the same way. No English relation names. No PATH.\n\n"
                    + "\n\n".join(demo_blocks[:k])
                    + "\n\n--- QUIZ ---\n"
                )

            body = (
                f"{preamble}"
                f"##### ID {cid} #####\n"
                f"START {start}\n"
                f"CONTEXT:\n{ctx}\n"
            )
            text = pack(
                f"ARM DEMO_{k}: {k} sealed demos; one quiz item; no PATH; no English hop wording.",
                body,
            )
            item_dir = arm_dir / f"item_{i}"
            item_dir.mkdir(exist_ok=True)
            path = item_dir / "prompt.txt"
            path.write_text(text)
            item_paths.append(repo_rel(path))

        arms_meta[arm_name] = {
            "n_demo": k,
            "n_quiz": N_QUIZ,
            "ids": ids,
            "item_paths": item_paths,
            "protocol": "one_quiz_per_file",
        }

    # --- LEGEND (batched OK — binder explicit) ---
    legend = (
        "LEGEND (relation roles only — entities stay sealed):\n"
        f"  {r1} = employment edge (person → company)\n"
        f"  {r2} = headquarters edge (company → city)\n"
        f"Follow {r1} then {r2} from START.\n"
    )
    legend_items = []
    legend_paths = []
    for i, row in enumerate(quiz):
        item_rng = random.Random(SEED + 5000 + i)
        edges = shuffle_edges(ceo_hq_edges(row), item_rng)
        sealed = [sealer.triple(*e) for e in edges]
        ctx = SealRouter(sealed).render()
        start = sealer.atom(row["person"])
        cid = f"DI_LEGEND_{i}"
        body = (
            f"##### ID {cid} #####\n"
            f"START {start}\n"
            f"{legend}\n"
            f"CONTEXT:\n{ctx}\n"
        )
        text = pack(
            "ARM LEGEND: English relation-role legend + sealed graph; one item.",
            body,
        )
        item_dir = RUNS / "LEGEND_ONLY" / f"item_{i}"
        item_dir.mkdir(parents=True, exist_ok=True)
        path = item_dir / "prompt.txt"
        path.write_text(text)
        legend_items.append(cid)
        legend_paths.append(repo_rel(path))
    arms_meta["LEGEND"] = {
        "n_demo": 0,
        "n_quiz": N_QUIZ,
        "ids": legend_items,
        "item_paths": legend_paths,
        "protocol": "one_quiz_per_file",
    }

    # --- PATH ceiling ---
    path_ids = []
    path_paths = []
    for i, row in enumerate(quiz):
        item_rng = random.Random(SEED + 6000 + i)
        edges = shuffle_edges(ceo_hq_edges(row), item_rng)
        sealed = [sealer.triple(*e) for e in edges]
        ctx = SealRouter(sealed).render()
        prog = path_program(
            row["person"], ("works_at", "headquartered_in"), row["hq"]
        ).seal(sealer)
        cid = f"DI_PATH_{i}"
        text = pack(
            "ARM PATH: gold PATH binder ceiling; one item.",
            f"Follow PATH over sealed CONTEXT. Output final sealed atom only.\n\n"
            f"##### ID {cid} #####\n{prog.body}\n\nCONTEXT:\n{ctx}\n",
        )
        item_dir = RUNS / "PATH_ONLY" / f"item_{i}"
        item_dir.mkdir(parents=True, exist_ok=True)
        path = item_dir / "prompt.txt"
        path.write_text(text)
        path_ids.append(cid)
        path_paths.append(repo_rel(path))
    arms_meta["PATH"] = {
        "n_demo": 0,
        "n_quiz": N_QUIZ,
        "ids": path_ids,
        "item_paths": path_paths,
        "protocol": "one_quiz_per_file",
    }

    harness = {
        "claim": (
            "Demo-only induction under opacity (v2): one-quiz-per-file; no English "
            "hop wording on DEMO arms; measure how many sealed demos restore 2-hop."
        ),
        "version": 2,
        "seed": SEED,
        "n_quiz": N_QUIZ,
        "ks": list(KS),
        "key_tag": "oir-demo-induction-v2",
        "rel_seals": {"works_at": r1, "headquartered_in": r2},
        "demo_people": [d["person"] for d in demos],
        "quiz_people": [q["person"] for q in quiz],
        "cases": cases,
        "arms": arms_meta,
        "protocol": (
            "v2: one quiz per file; edge shuffle; no English two-hop on DEMO; "
            "demos disjoint from quiz; v1 batch+two-hop discarded as confound"
        ),
        "v1_discard": {
            "reason": "DEMO_0 8/8 via within-batch isomorphic induction + English two-hop leak",
            "action": "do not cite v1 scores",
        },
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "demo_induction_harness.json").write_text(json.dumps(harness, indent=2))
    n_prompts = sum(len(a["item_paths"]) for a in arms_meta.values())
    print(json.dumps({"n_prompts": n_prompts, "arms": list(arms_meta)}, indent=2))
    print("wrote", RESULTS / "demo_induction_harness.json")


if __name__ == "__main__":
    build()
