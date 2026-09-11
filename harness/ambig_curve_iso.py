#!/usr/bin/env python3
"""Ambiguity curve: number of same-type 2-hops k=1..5 on public Wikidata CEOs.

Start in q. Entities English. Relations HMAC'd. Gold is always
works_at → headquartered_in. Extra paths use distinct relation pairs with
city tails (same type). k=5 also has a plan arm.
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

from paths import repo_rel
from factorial_2x2_iso import SOURCE, pack  # type: ignore
from oir import EntitySeal, SealRouter, path_program
from oir.adapters import load_json_records

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "ambig_curve_iso"
SEED = 20260821
N = 32
KEY_BASE = b"oir-ambig-curve-iso-v1"
KS = (1, 2, 3, 4, 5)
DECOY_PAIRS = [
    ("partner_of", "located_in"),
    ("owns_stake_in", "based_in"),
    ("advises", "registered_in"),
    ("founded", "incorporated_in"),
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


def edges_for_k(row: dict, decoys: list[dict], k: int) -> list[tuple[str, str, str]]:
    p, c, hq = row["person"], row["company"], row["hq"]
    edges = [(p, "works_at", c), (c, "headquartered_in", hq)]
    for j in range(k - 1):
        d = decoys[j]
        r1, r2 = DECOY_PAIRS[j]
        edges.append((p, r1, d["company"]))
        edges.append((d["company"], r2, d["hq"]))
    return edges


def render(edges, sealer: EntitySeal) -> str:
    return SealRouter([(h, sealer.atom(r), t) for h, r, t in edges]).render()


def build() -> dict:
    recs = load_json_records(SOURCE)
    rng = random.Random(SEED)
    pool = [r for r in recs if r["hq"] and r["person"] and r["company"]]
    picked = rng.sample(pool, N)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)
    arm_names = [f"K{k}" for k in KS] + ["K5_PLAN"]
    arms = {a: {"ids": [], "item_paths": []} for a in arm_names}
    cases = []
    for i, row in enumerate(picked):
        used_co, used_hq = {row["company"]}, {row["hq"]}
        decoys = []
        for r in pool:
            if r["company"] in used_co or r["hq"] in used_hq or r["person"] == row["person"]:
                continue
            decoys.append(r)
            used_co.add(r["company"])
            used_hq.add(r["hq"])
            if len(decoys) == 4:
                break
        assert len(decoys) == 4
        assert len({d["hq"] for d in decoys} | {row["hq"]}) == 5
        sealer = EntitySeal(item_key(i))
        q = (
            "What city is the headquarters of the company led by "
            f"{row['person']}?"
        )
        ids = {}
        decoy_city = decoys[0]["hq"]
        for k in KS:
            e = edges_for_k(row, decoys, k)
            hops = two_hops(e, row["person"])
            assert len(hops) == k, (k, hops)
            gold_hops = [h for h in hops if h[2] == row["hq"]]
            assert len(gold_hops) == 1
            ctx = render(e, sealer)
            arm = f"K{k}"
            cid = f"CURVE_{arm}_{i}"
            ids[arm] = cid
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                pack(
                    cid,
                    q,
                    ctx,
                    sealed_ans=False,
                    extra=f"ARM {arm}: opaque relations; {k} same-type 2-hop(s) from start.",
                )
            )
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        plan = path_program(
            row["person"],
            (sealer.atom("works_at"), sealer.atom("headquartered_in")),
            row["hq"],
        )
        ctx5 = render(edges_for_k(row, decoys, 5), sealer)
        cid = f"CURVE_K5_PLAN_{i}"
        ids["K5_PLAN"] = cid
        path = RUNS / "K5_PLAN" / f"item_{i}" / "prompt.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            pack(
                cid,
                q + "\n\n" + plan.body,
                ctx5,
                sealed_ans=False,
                extra="ARM K5_PLAN: k=5 graph plus explicit sealed relation sequence.",
            )
        )
        arms["K5_PLAN"]["ids"].append(cid)
        arms["K5_PLAN"]["item_paths"].append(repo_rel(path))
        cases.append(
            {
                "i": i,
                "person": row["person"],
                "ids": ids,
                "gold": row["hq"],
                "decoy_hq": decoy_city,
            }
        )
    harness = {
        "n": N,
        "seed": SEED,
        "protocol": "isolation",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_public": "Wikidata CEO records; k extra same-type city tails",
        "keys": "per-item HMAC on relation atoms; entities English; start in q",
        "start_in_question": True,
        "ks": list(KS),
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "ambig_curve_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2, ensure_ascii=False) + "\n")
    print("wrote", out)
    return harness


if __name__ == "__main__":
    build()
