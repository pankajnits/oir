#!/usr/bin/env python3
"""Entity × relation opacity on the same Wikidata 2×2 graphs.

Completes the ARoG-relevant ablation the relation-only factorial left open:
  EE  English entities, English relations   (already scored as ENG_* — not re-run)
  EO  English entities, opaque relations    (already scored as OPAQUE_* — not re-run)
  OE  opaque entities, English relations    (ARoG-like: readable predicates)
  OO  opaque entities, opaque relations     (full OIR; start seal in q)

Start atom is always in the question. Same seed / 32 CEOs as factorial_2x2_iso.py.
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

from paths import repo_rel
from factorial_2x2_iso import (  # type: ignore
    N,
    SEED,
    SOURCE,
    ambig_edges,
    two_hops,
    unique_edges,
)
from oir import EntitySeal, SealRouter, path_program
from oir.adapters import load_json_records

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "entity_rel_2x2_iso"
KEY_BASE = b"oir-entrel-2x2-iso-v1"
ARMS = [
    "OE_UNIQUE",
    "OE_AMBIG",
    "OO_UNIQUE",
    "OO_AMBIG",
    "OO_AMBIG_PLAN",
]


def render(edges, sealer: EntitySeal, *, seal_ent: bool, seal_rel: bool) -> str:
    out = []
    for h, r, t in edges:
        hh = sealer.atom(h) if seal_ent else h
        rr = sealer.atom(r) if seal_rel else r
        tt = sealer.atom(t) if seal_ent else t
        out.append((hh, rr, tt))
    return SealRouter(out).render()


def pack(cid: str, q: str, ctx: str, extra: str) -> str:
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No other files.",
            f"Format: ANSWER_SEALED[{cid}]: <token_or_UNKNOWN>",
            extra,
            f"##### ID {cid} #####",
            "QUESTION:",
            q,
            "",
            "CONTEXT:",
            ctx,
            "",
        ]
    )


def picked_rows() -> list[dict]:
    recs = load_json_records(SOURCE)
    rng = random.Random(SEED)
    pool = [r for r in recs if r["hq"] and r["person"] and r["company"]]
    return rng.sample(pool, N)


def build() -> dict:
    picked = picked_rows()
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    arms = {
        a: {"ids": [], "item_paths": [], "sealed_answer": True} for a in ARMS
    }
    cases = []
    for i, row in enumerate(picked):
        decoy = picked[(i + 1) % N]
        if decoy["hq"] == row["hq"] or decoy["person"] == row["person"]:
            decoy = {
                "person": f"DecoyPerson_{i}",
                "company": f"DecoyCo_{i}",
                "hq": f"DecoyCity_{i}",
            }
        u_edges = unique_edges(row, decoy)
        a_edges = ambig_edges(row, decoy)
        assert len(two_hops(u_edges, row["person"])) == 1
        assert len(two_hops(a_edges, row["person"])) == 2

        # Independent keys from the relation-only factorial.
        sealer = EntitySeal(hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:16])
        start = sealer.atom(row["person"])
        gold = sealer.atom(row["hq"])
        decoy_tok = sealer.atom(decoy["hq"])
        q = (
            "What city is the headquarters of the company led by "
            f"{start}?"
        )
        assert start in q

        oe_u = render(u_edges, sealer, seal_ent=True, seal_rel=False)
        oe_a = render(a_edges, sealer, seal_ent=True, seal_rel=False)
        oo_u = render(u_edges, sealer, seal_ent=True, seal_rel=True)
        oo_a = render(a_edges, sealer, seal_ent=True, seal_rel=True)
        plan = path_program(
            start,
            (sealer.atom("works_at"), sealer.atom("headquartered_in")),
            gold,
        )
        r_oo = SealRouter(
            [
                (sealer.atom(h), sealer.atom(r), sealer.atom(t))
                for h, r, t in a_edges
            ]
        )
        assert r_oo.path(start, [sealer.atom("works_at"), sealer.atom("headquartered_in")]) == [
            gold
        ]

        specs = {
            "OE_UNIQUE": (
                q,
                oe_u,
                "ARM OE_UNIQUE: opaque entities, English relations; one 2-hop.",
            ),
            "OE_AMBIG": (
                q,
                oe_a,
                "ARM OE_AMBIG: opaque entities, English relations; two 2-hops.",
            ),
            "OO_UNIQUE": (
                q,
                oo_u,
                "ARM OO_UNIQUE: opaque entities and relations; one 2-hop; start seal in q.",
            ),
            "OO_AMBIG": (
                q,
                oo_a,
                "ARM OO_AMBIG: opaque entities and relations; two 2-hops; start seal in q.",
            ),
            "OO_AMBIG_PLAN": (
                q + "\n\n" + plan.body,
                oo_a,
                "ARM OO_AMBIG_PLAN: same OO_AMBIG graph plus explicit sealed relation sequence.",
            ),
        }
        ids, golds, decoys = {}, {}, {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"ER22_{arm}_{i}"
            ids[arm] = cid
            golds[arm] = gold
            decoys[arm] = decoy_tok
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, qq, ctx, header))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

        cases.append(
            {
                "i": i,
                "person": row["person"],
                "hq": row["hq"],
                "ids": ids,
                "gold": gold,
                "decoy_hq": decoy_tok,
                "golds": golds,
                "decoys": decoys,
            }
        )

    harness = {
        "n": N,
        "seed": SEED,
        "protocol": "isolation",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_public": "Wikidata-derived CEO→company→HQ slice (73 records in-repo)",
        "keys": "per-item HMAC; OE seals entities only; OO seals entities and relations",
        "start_in_question": True,
        "factors": ["entity_lexicality", "relation_lexicality", "path_determinacy"],
        "arms": arms,
        "cases": cases,
        "note": "EE/EO cells live in factorial_2x2_iso_gpt56.json (same people, start in q).",
    }
    out = RESULTS / "entity_rel_2x2_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print("wrote", out, "n", N)
    return harness


if __name__ == "__main__":
    build()
