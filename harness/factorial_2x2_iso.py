#!/usr/bin/env python3
"""Matched 2x2 isolation suite from public Wikidata CEO records.

Factors (start atom always in the question, same entities/template/hop count):
  relation lexicality: English vs opaque relations (entities stay English)
  path determinacy: unique 2-hop from start vs two 2-hops from start

Plus OPAQUE_AMBIG_PLAN: gold sealed relation sequence (execution upper bound).

Does not overwrite CEO n=32 three-arm prompts.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program
from paths import repo_rel
from oir.adapters import load_json_records

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "factorial_2x2_iso"
SOURCE = ROOT / "data" / "real" / "wikidata_ceo_hops_v2.json"
SEED = 20260821
N = 32
KEY_BASE = b"oir-fact-2x2-iso-v1"
ARMS = [
    "ENG_UNIQUE",
    "ENG_AMBIG",
    "OPAQUE_UNIQUE",
    "OPAQUE_AMBIG",
    "OPAQUE_AMBIG_PLAN",
]


def item_key(i: int) -> bytes:
    return hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:16]


def two_hops(edges: list[tuple[str, str, str]], start: str) -> list[tuple[str, str, str]]:
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for h, r, t in edges:
        out[h].append((r, t))
    found: list[tuple[str, str, str]] = []
    for r1, mid in out.get(start, []):
        for r2, tail in out.get(mid, []):
            found.append((r1, r2, tail))
    return found


def unique_edges(row: dict, decoy: dict) -> list[tuple[str, str, str]]:
    p, c, hq = row["person"], row["company"], row["hq"]
    return [
        (p, "works_at", c),
        (c, "headquartered_in", hq),
        (decoy["person"], "works_at", decoy["company"]),
        (decoy["company"], "headquartered_in", decoy["hq"]),
    ]


def ambig_edges(row: dict, decoy: dict) -> list[tuple[str, str, str]]:
    p, c, hq = row["person"], row["company"], row["hq"]
    return [
        (p, "works_at", c),
        (c, "headquartered_in", hq),
        (p, "partner_of", decoy["company"]),
        (decoy["company"], "located_in", decoy["hq"]),
    ]


def render(edges: list[tuple[str, str, str]], sealer: EntitySeal | None) -> str:
    if sealer is None:
        return SealRouter(edges).render()
    sealed = [(h, sealer.atom(r), t) for h, r, t in edges]
    return SealRouter(sealed).render()


def pack(cid: str, q: str, ctx: str, *, sealed_ans: bool, extra: str = "") -> str:
    fmt = (
        f"Format: ANSWER_SEALED[{cid}]: <token_or_UNKNOWN>"
        if sealed_ans
        else f"Format: ANSWER_PLAIN[{cid}]: <city_or_UNKNOWN>"
    )
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No other files.",
        fmt,
        extra,
        f"##### ID {cid} #####",
        "QUESTION:",
        q,
        "",
        "CONTEXT:",
        ctx,
        "",
    ]
    return "\n".join(x for x in lines if x is not None)


def build() -> dict:
    recs = load_json_records(SOURCE)
    rng = random.Random(SEED)
    pool = [r for r in recs if r["hq"] and r["person"] and r["company"]]
    picked = rng.sample(pool, N)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    arms = {a: {"ids": [], "item_paths": []} for a in ARMS}
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
        EntitySeal.assert_raw_injective(x for e in (*u_edges, *a_edges) for x in e)
        u_hops = two_hops(u_edges, row["person"])
        a_hops = two_hops(a_edges, row["person"])
        assert len(u_hops) == 1, u_hops
        assert len(a_hops) == 2, a_hops
        assert u_hops[0][2] == row["hq"]
        gold_hops = [h for h in a_hops if h[2] == row["hq"]]
        assert len(gold_hops) == 1

        sealer = EntitySeal(item_key(i))
        q = (
            "What city is the headquarters of the company led by "
            f"{row['person']}?"
        )
        assert row["person"] in q
        u_eng = render(u_edges, None)
        a_eng = render(a_edges, None)
        u_op = render(u_edges, sealer)
        a_op = render(a_edges, sealer)
        plan = path_program(
            row["person"],
            (sealer.atom("works_at"), sealer.atom("headquartered_in")),
            row["hq"],
        )
        router_u = SealRouter([(h, sealer.atom(r), t) for h, r, t in u_edges])
        router_a = SealRouter([(h, sealer.atom(r), t) for h, r, t in a_edges])
        gold_path = [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        assert router_u.path(row["person"], gold_path) == [row["hq"]]
        assert router_a.path(row["person"], gold_path) == [row["hq"]]

        specs = {
            "ENG_UNIQUE": (q, u_eng, False, "ARM ENG_UNIQUE: English relations; one 2-hop from start."),
            "ENG_AMBIG": (q, a_eng, False, "ARM ENG_AMBIG: English relations; two 2-hops from start."),
            "OPAQUE_UNIQUE": (q, u_op, False, "ARM OPAQUE_UNIQUE: opaque relations, English entities; one 2-hop from start."),
            "OPAQUE_AMBIG": (q, a_op, False, "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start."),
            "OPAQUE_AMBIG_PLAN": (
                q + "\n\n" + plan.body,
                a_op,
                False,
                "ARM OPAQUE_AMBIG_PLAN: same graph as OPAQUE_AMBIG plus explicit relation sequence.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, sealed_ans, header) in specs.items():
            cid = f"F22_{arm}_{i}"
            ids[arm] = cid
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, qq, ctx, sealed_ans=sealed_ans, extra=header))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

        cases.append(
            {
                "i": i,
                "person": row["person"],
                "company": row["company"],
                "hq": row["hq"],
                "decoy_hq": decoy["hq"],
                "unique_hops": len(u_hops),
                "ambig_hops": len(a_hops),
                "ids": ids,
                "gold": row["hq"],
            }
        )

    harness = {
        "n": N,
        "seed": SEED,
        "protocol": "isolation",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_public": "Wikidata-derived CEO→company→HQ slice (73 records in-repo)",
        "keys": "per-item HMAC on relation atoms only; entities remain English",
        "start_in_question": True,
        "factors": ["relation_lexicality", "path_determinacy"],
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "factorial_2x2_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print("wrote", out, "n", N)
    return harness


if __name__ == "__main__":
    build()
