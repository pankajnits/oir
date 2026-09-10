#!/usr/bin/env python3
"""Dual-path matched vs novel seals on public WikiMovies / MetaQA facts.

Same protocol as the synthetic dual-path suite (START seal, full OIR, 4 demos),
but every node is a real movie/person from wiki_entities_kb.txt.
Per-item HMAC so demos and quiz share seals only within that file.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program
from paths import repo_rel

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "dualpath_wikimovies_iso"
FREEZE = ROOT / "data" / "metaqa" / "oir_2hop_people_n32.json"
KEY_BASE = b"oir-dp-wikimovies-iso-v1"
N_DEMO = 4
ARMS = ["MATCHED", "NOVEL", "PLAN"]


def item_key(i: int) -> bytes:
    return hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:16]


def pack(cid: str, header: str, body: str) -> str:
    return (
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.\n"
        f"Format: ANSWER_SEALED[{cid}]: <seal_or_UNKNOWN>\n\n"
        f"{header}\n\n"
        f"{body}\n"
    )


def unique_edges(row: dict) -> list[tuple[str, str, str]]:
    return [
        (row["actor"], "starred_in", row["movie"]),
        (row["movie"], "directed_by", row["director"]),
    ]


def ambig_edges(row: dict) -> list[tuple[str, str, str]]:
    return [
        (row["actor"], "starred_in", row["movie"]),
        (row["movie"], "directed_by", row["director"]),
        (row["movie"], "written_by", row["writer"]),
    ]


def novel_ambig_edges(row: dict) -> list[tuple[str, str, str]]:
    return [
        (row["actor"], "appeared_in_quiz", row["movie"]),
        (row["movie"], "helmed_by_quiz", row["director"]),
        (row["movie"], "scripted_by_quiz", row["writer"]),
    ]


def demo_block(j: int, row: dict, sealer: EntitySeal) -> str:
    edges = unique_edges(row)
    sealed = [sealer.triple(*e) for e in edges]
    start = sealer.atom(row["actor"])
    gold = sealer.atom(row["director"])
    ctx = SealRouter(sealed).render()
    rels = [sealer.atom("starred_in"), sealer.atom("directed_by")]
    assert SealRouter(sealed).path(start, rels) == [gold]
    return f"DEMO {j}:\nSTART {start}\nCONTEXT:\n{ctx}\nANSWER_SEALED: {gold}"


def build() -> dict:
    items = json.loads(FREEZE.read_text())["items"]
    assert len(items) >= 32
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    arms = {a: {"ids": [], "item_paths": [], "sealed_answer": True} for a in ARMS}
    cases = []
    n = len(items)
    for i, row in enumerate(items):
        sealer = EntitySeal(item_key(i))
        demos = [items[(i + 1 + j) % n] for j in range(N_DEMO)]
        blocks = "\n\n".join(demo_block(j, d, sealer) for j, d in enumerate(demos))
        preamble = (
            "Learn the mapping from DEMOs (same encoding).\n"
            "Answer the QUIZ the same way. No English relation names. No PATH.\n"
            "If ambiguous, UNKNOWN.\n\n"
            + blocks
            + "\n\n--- QUIZ ---\n"
        )
        start = sealer.atom(row["actor"])
        gold = sealer.atom(row["director"])
        trap = sealer.atom(row["writer"])

        matched_sealed = [sealer.triple(*e) for e in ambig_edges(row)]
        novel_sealed = [sealer.triple(*e) for e in novel_ambig_edges(row)]
        m_ctx = SealRouter(matched_sealed).render()
        n_ctx = SealRouter(novel_sealed).render()
        assert SealRouter(matched_sealed).path(
            start, [sealer.atom("starred_in"), sealer.atom("directed_by")]
        ) == [gold]
        assert SealRouter(matched_sealed).path(
            start, [sealer.atom("starred_in"), sealer.atom("written_by")]
        ) == [trap]
        assert SealRouter(novel_sealed).path(
            start, [sealer.atom("appeared_in_quiz"), sealer.atom("helmed_by_quiz")]
        ) == [gold]

        plan = path_program(
            start,
            (sealer.atom("starred_in"), sealer.atom("directed_by")),
            gold,
        )

        specs = {
            "MATCHED": (
                "ARM MATCHED: demos expose gold relation seals; quiz has a decoy path.",
                preamble + f"##### ID DPWM_MATCHED_{i} #####\nSTART {start}\nCONTEXT:\n{m_ctx}\n",
                gold,
                trap,
                m_ctx,
            ),
            "NOVEL": (
                "ARM NOVEL: demo seals do not appear on the quiz gold route.",
                preamble + f"##### ID DPWM_NOVEL_{i} #####\nSTART {start}\nCONTEXT:\n{n_ctx}\n",
                gold,
                trap,
                n_ctx,
            ),
            "PLAN": (
                "ARM PLAN: explicit sealed relation sequence on the MATCHED graph.",
                (
                    "Follow PATH over sealed CONTEXT. Output final sealed atom only.\n\n"
                    f"##### ID DPWM_PLAN_{i} #####\n{plan.body}\n\nCONTEXT:\n{m_ctx}\n"
                ),
                gold,
                trap,
                m_ctx,
            ),
        }
        ids = {}
        for arm, (header, body, g, t, _) in specs.items():
            cid = f"DPWM_{arm}_{i}"
            ids[arm] = cid
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, header, body))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

        cases.append(
            {
                "i": i,
                "actor": row["actor"],
                "movie": row["movie"],
                "ids": ids,
                "gold": gold,
                "decoy_hq": trap,
                "golds": {a: gold for a in ARMS},
                "decoys": {a: trap for a in ARMS},
            }
        )

    harness = {
        "n": n,
        "seed": json.loads(FREEZE.read_text())["seed"],
        "protocol": "isolation",
        "source": str(FREEZE.relative_to(ROOT)),
        "source_public": "WikiMovies / MetaQA movie KB (director vs writer, same freeze as 2x2)",
        "keys": "per-item HMAC on entities and relations; demos share the item key",
        "start_in_question": True,
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "dualpath_wikimovies_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print("wrote", out, "n", n)
    return harness


if __name__ == "__main__":
    build()
