#!/usr/bin/env python3
"""
Edge-order confound for OOD nohandle successes.

Hypothesis: nohandle 'passes' by taking the first company→sink relation in
file order (city listed before owned_by), not by understanding stationed_in.

Flip: list owned_by BEFORE city relation. If nohandle collapses or picks Hold,
order heuristic is confirmed. Handles should still get the city.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KEY = b"oir-edge-order-confound-v1"


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


def graph(i, twin):
    alice = f"Alice{i}"
    acme, beta = f"Acme{i}", f"Beta{i}"
    cx, cy = f"CityX{i}", f"CityY{i}"
    # owned_by FIRST, then stationed_in
    edges = [
        (f"Bob{i}", "works_at", beta),
        (acme, "owned_by", f"Hold{i}"),
        (beta, "owned_by", f"HoldB{i}"),
        (acme, "stationed_in", cx),
        (beta, "stationed_in", cy),
    ]
    if twin == "A":
        edges = [(alice, "works_at", acme)] + edges
        ans, wrong = cx, f"Hold{i}"
    else:
        edges = [(alice, "works_at", beta)] + edges
        ans, wrong = cy, f"HoldB{i}"
    return edges, alice, ans, wrong


def main():
    sealer = EntitySeal(KEY)
    cases = []
    for i in range(4):
        for twin in ("A", "B"):
            edges, alice, ans, wrong = graph(i, twin)
            q = f"What city is associated with the employer of {sealer.atom(alice)}? City seal only."
            for cond, handles in {
                "handles": f"""Handles:
employer_rel={sealer.atom('works_at')}
city_rel={sealer.atom('stationed_in')}
Join person-employer_rel→co ; co-city_rel→city. Ignore other relations.
""",
                "nohandle": """English plan only (no seal bindings): join works_at then stationed_in.
All CONTEXT atoms are opaque seals.
""",
            }.items():
                cid = f"EOC_G{i}_{twin}_{cond}"
                body = f"""OPAQUE JOIN — no decryption.
{handles}
QUESTION:
{q}

CONTEXT:
{render(sealer, edges)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
                d = ROOT / "runs" / f"eoc_{cond}_ONLY"
                d.mkdir(parents=True, exist_ok=True)
                path = d / f"{cid}.txt"
                path.write_text("MODEL UNDER TEST. No tools. Read ONLY this file.\n\n=== QUIZ ===\n" + body)
                cases.append(
                    {
                        "id": cid,
                        "condition": cond,
                        "expect_sealed": sealer.atom(ans),
                        "wrong_hold_seal": sealer.atom(wrong),
                        "expect_plain": ans,
                        "payload": str(path),
                    }
                )

    for cond in ("handles", "nohandle"):
        subset = [c for c in cases if c["condition"] == cond]
        d = ROOT / "runs" / f"eoc_{cond}_ONLY"
        lines = [
            "MODEL UNDER TEST. No tools. Read ONLY this file. Answer EVERY ID.\n",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (d / f"BATCH_{cond}.txt").write_text("\n".join(lines))

    (RESULTS / "edge_order_harness.json").write_text(
        json.dumps({"n": len(cases), "rev": sealer.rev, "cases": cases}, indent=2)
    )
    print(json.dumps({"n": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
