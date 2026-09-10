#!/usr/bin/env python3
"""WikiMovies people 2×2 n=100, Condition B: hash question verbs on opaque arms.

Reuses data/metaqa/oir_2hop_people_n100.json (WikiMovies / MetaQA movie graph).
Does not overwrite the Condition A n=100 prompts (those leak directed/starred).
English arms are not rebuilt: cite metaqa_2x2_people_n100_iso_*.json.

ARM headers name topology only (same wording as the Wikidata 2×2). They do not
name director/writer. The previous banner lock is
results/metaqa_2x2_people_n100_qhash_iso_gpt56_arm_banner_v1.json.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from paths import repo_rel
from factorial_2x2_iso import two_hops as hops  # type: ignore
from metaqa_2x2_iso import ambig_edges, pack, render, unique_edges  # type: ignore
from metaqa_official_iso import hash_q_keep_entity  # type: ignore
from oir import EntitySeal, path_program

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "metaqa_2x2_people_n100_qhash_iso"
FREEZE = ROOT / "data" / "metaqa" / "oir_2hop_people_n100.json"
KEY_BASE = b"oir-metaqa-2x2-people-n100-qhash-v1"
ARMS = ["OPAQUE_UNIQUE", "OPAQUE_AMBIG", "OPAQUE_AMBIG_PLAN"]
LEAK = ("directed", "starred", "written", "writer", "director")


def item_key(i: int) -> bytes:
    return hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:16]


def build() -> dict:
    freeze = json.loads(FREEZE.read_text())
    picked = freeze["items"]
    n = len(picked)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)
    arms = {a: {"ids": [], "item_paths": []} for a in ARMS}
    cases = []
    for i, row in enumerate(picked):
        decoy = next(
            picked[(i + k) % n]
            for k in range(1, n)
            if picked[(i + k) % n]["actor"] != row["actor"]
            and picked[(i + k) % n]["movie"] != row["movie"]
        )
        u_edges = unique_edges(row, decoy)
        a_edges = list(dict.fromkeys(ambig_edges(row, decoy)))
        assert len(hops(u_edges, row["actor"])) == 1
        assert len(hops(a_edges, row["actor"])) == 2
        sealer = EntitySeal(item_key(i))
        q_raw = f"Who directed a movie that [{row['actor']}] starred in?"
        q = hash_q_keep_entity(q_raw, row["actor"], sealer)
        q_head = q.split("CONTEXT:")[0].lower()
        for w in LEAK:
            if w in q_head:
                raise SystemExit(f"verb leak in hashed question item {i}: {q!r}")
        if f"[{row['actor']}]" not in q:
            raise SystemExit(f"start missing from hashed q item {i}")
        plan = path_program(
            row["actor"],
            (sealer.atom("starred_in"), sealer.atom("directed_by")),
            row["director"],
        )
        specs = {
            "OPAQUE_UNIQUE": (
                q,
                render(u_edges, sealer),
                "ARM OPAQUE_UNIQUE: opaque relations, English entities; one 2-hop from start.",
            ),
            "OPAQUE_AMBIG": (
                q,
                render(a_edges, sealer),
                "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start.",
            ),
            "OPAQUE_AMBIG_PLAN": (
                q + "\n\n" + plan.body,
                render(a_edges, sealer),
                "ARM OPAQUE_AMBIG_PLAN: opaque relations, English entities; two 2-hops from start; explicit join plan.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"MQA100B_{arm}_{i}"
            ids[arm] = cid
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, qq, ctx, header))
            blob = path.read_text().lower()
            for w in LEAK:
                if w in blob:
                    raise SystemExit(f"verb leak in {arm} item {i}: {w!r}")
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append(
            {
                "i": i,
                **row,
                "ids": ids,
                "gold": row["director"],
                "decoy_hq": row["writer"],
            }
        )
    harness = {
        "n": n,
        "seed": freeze["seed"],
        "protocol": "isolation",
        "condition": "B",
        "source": "WikiMovies / MetaQA movie graph; same 100 items as Condition A freeze",
        "source_url": "https://github.com/rohit129/Movie_KnowledgeGraph_QA/blob/master/wiki_entities_kb.txt",
        "freeze": str(FREEZE.relative_to(ROOT)),
        "start_in_question": True,
        "keys": "per-item HMAC; question atoms hashed except bracketed start; ARM headers name topology only",
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "metaqa_2x2_people_n100_qhash_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2) + "\n")
    print("wrote", out, "n", n)
    return harness


if __name__ == "__main__":
    build()
