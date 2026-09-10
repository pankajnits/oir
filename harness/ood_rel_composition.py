#!/usr/bin/env python3
"""
OOD relation composition (novelty stress).

Train-like vocabulary in handles uses familiar English glosses mapped to seals,
but the *second* hop uses a held-out relation name never seen in prior L3–L7
prompts (e.g. domiciled_at instead of located_in).

Question: does the model follow the opaque handle binding for a novel relation
token, or does it rely on pretrained English 'located_in' priors?

Conditions (isolated dirs):
  in_dist   — works_at + located_in (baseline)
  ood_rel   — works_at + domiciled_at (held-out relation; handle provides seal)
  ood_nohandle — domiciled_at in graph, English plan only, no seal binding
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KEY = b"oir-ood-rel-comp-v1"


class EntitySeal:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def atom(self, a: str) -> str:
        if a not in self.fwd:
            d = hmac.new(self.key, a.encode(), hashlib.sha256).digest()
            t = "E" + d[:6].hex()
            self.fwd[a] = t
            self.rev[t] = a
        return self.fwd[a]


def render(sealer, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def graph(i, twin, city_rel: str):
    alice = f"Alice{i}"
    acme, beta = f"Acme{i}", f"Beta{i}"
    cx, cy = f"CityX{i}", f"CityY{i}"
    edges = [
        (f"Bob{i}", "works_at", beta),
        (acme, city_rel, cx),
        (beta, city_rel, cy),
        (acme, "owned_by", f"Hold{i}"),
        (beta, "owned_by", f"HoldB{i}"),
    ]
    if twin == "A":
        edges = [(alice, "works_at", acme)] + edges
        ans = cx
    else:
        edges = [(alice, "works_at", beta)] + edges
        ans = cy
    return edges, alice, ans, acme if twin == "A" else beta


def write_batch(cond: str, cases_subset, sealer):
    d = ROOT / "runs" / f"ood_{cond}_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file. Answer EVERY ID.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
    ]
    for c in cases_subset:
        quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
        lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
    (d / f"BATCH_{cond}.txt").write_text("\n".join(lines))
    return str(d / f"BATCH_{cond}.txt")


def main():
    sealer = EntitySeal(KEY)
    cases = []
    # Pre-warm seals
    for rel in ("works_at", "located_in", "domiciled_at", "owned_by"):
        sealer.atom(rel)

    for i in range(4):
        for twin in ("A", "B"):
            # --- in_dist ---
            edges, alice, ans, mid = graph(i, twin, "located_in")
            q = f"What city is associated with the employer of {sealer.atom(alice)}? City seal only."
            body = f"""OPAQUE JOIN — no decryption.
Handles:
employer_rel={sealer.atom('works_at')}
city_rel={sealer.atom('located_in')}
Join person-employer_rel→co ; co-city_rel→city.

QUESTION:
{q}

CONTEXT:
{render(sealer, edges)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
            d = ROOT / "runs" / "ood_in_dist_ONLY"
            d.mkdir(parents=True, exist_ok=True)
            cid = f"OOD_G{i}_{twin}_in_dist"
            path = d / f"{cid}.txt"
            path.write_text("MODEL UNDER TEST. No tools. Read ONLY this file.\n\n=== QUIZ ===\n" + body)
            cases.append(
                {
                    "id": cid,
                    "condition": "in_dist",
                    "expect_sealed": sealer.atom(ans),
                    "expect_plain": ans,
                    "mid": sealer.atom(mid),
                    "payload": str(path),
                }
            )

            # --- ood_rel with handles ---
            edges2, alice, ans, mid = graph(i, twin, "domiciled_at")
            body2 = f"""OPAQUE JOIN — no decryption.
Handles (note: city_rel is a FRESH relation name; follow the seal binding):
employer_rel={sealer.atom('works_at')}
city_rel={sealer.atom('domiciled_at')}
Join person-employer_rel→co ; co-city_rel→city.

QUESTION:
{q}

CONTEXT:
{render(sealer, edges2)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
            d2 = ROOT / "runs" / "ood_ood_rel_ONLY"
            d2.mkdir(parents=True, exist_ok=True)
            cid2 = f"OOD_G{i}_{twin}_ood_rel"
            path2 = d2 / f"{cid2}.txt"
            path2.write_text("MODEL UNDER TEST. No tools. Read ONLY this file.\n\n=== QUIZ ===\n" + body2)
            cases.append(
                {
                    "id": cid2,
                    "condition": "ood_rel",
                    "expect_sealed": sealer.atom(ans),
                    "expect_plain": ans,
                    "mid": sealer.atom(mid),
                    "payload": str(path2),
                }
            )

            # --- ood no handle: English says follow domiciled_at but no seal ---
            body3 = f"""OPAQUE JOIN — no decryption.
English plan only (no seal bindings): join works_at then domiciled_at.
All atoms including relations are opaque seals in CONTEXT.

QUESTION:
{q}

CONTEXT:
{render(sealer, edges2)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
            d3 = ROOT / "runs" / "ood_ood_nohandle_ONLY"
            d3.mkdir(parents=True, exist_ok=True)
            cid3 = f"OOD_G{i}_{twin}_ood_nohandle"
            path3 = d3 / f"{cid3}.txt"
            path3.write_text("MODEL UNDER TEST. No tools. Read ONLY this file.\n\n=== QUIZ ===\n" + body3)
            cases.append(
                {
                    "id": cid3,
                    "condition": "ood_nohandle",
                    "expect_sealed": sealer.atom(ans),
                    "expect_plain": ans,
                    "mid": sealer.atom(mid),
                    "payload": str(path3),
                }
            )

    for cond in ("in_dist", "ood_rel", "ood_nohandle"):
        write_batch(cond, [c for c in cases if c["condition"] == cond], sealer)

    (RESULTS / "ood_rel_harness.json").write_text(
        json.dumps(
            {
                "benchmark": "ood_relation_composition",
                "held_out_relation": "domiciled_at",
                "n": len(cases),
                "rev": sealer.rev,
                "cases": cases,
            },
            indent=2,
        )
    )
    print(json.dumps({"n": len(cases), "per_cond": 8}, indent=2))


if __name__ == "__main__":
    main()
