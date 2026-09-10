#!/usr/bin/env python3
"""
Multi-out-edge confound for nohint / schema_only success.

Hypothesis: prior none/schema_only successes used structural uniqueness —
companies only emit located_in. If companies also emit owned_by / founded_in /
partner_of to distractor tails, second hop is ambiguous without located_in grounding.

Conditions (4 graphs × 2 twins):
  opaque_rel — relation seal handles (should still PASS)
  none       — no handles (should FAIL or become unreliable vs unique-schema graphs)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "multi_out_confound"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)
KEY = b"oir-multi-out-confound-v1"


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

    def text(self, s: str) -> str:
        return "".join(
            self.atom(p) if re.fullmatch(r"[A-Za-z0-9_]+", p) else p
            for p in re.findall(r"[A-Za-z0-9_]+|[^A-Za-z0-9_]+", s)
        )


def render(sealer, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def graph_i(i, twin):
    alice, bob = f"Alice{i}", f"Bob{i}"
    acme, beta = f"Acme{i}", f"Beta{i}"
    cx, cy = f"CityX{i}", f"CityY{i}"
    # Multiple out-edges from each company
    decoys = [
        (acme, "owned_by", f"HoldCo{i}"),
        (acme, "founded_in", f"Year{i}A"),
        (acme, "partner_of", f"Partner{i}A"),
        (beta, "owned_by", f"HoldCo{i}B"),
        (beta, "founded_in", f"Year{i}B"),
        (beta, "partner_of", f"Partner{i}B"),
        (bob, "works_at", beta),
        (acme, "located_in", cx),
        (beta, "located_in", cy),
    ]
    if twin == "A":
        edges = [(alice, "works_at", acme)] + decoys
        ans, mid = cx, acme
    else:
        edges = [(alice, "works_at", beta)] + decoys
        ans, mid = cy, beta
    return edges, alice, ans, mid


def main():
    sealer = EntitySeal(KEY)
    cases = []
    for i in range(4):
        for twin in ("A", "B"):
            edges, alice, ans, mid = graph_i(i, twin)
            q = f"Where is the company located that {alice} works_at? City only."
            ans_s, mid_s = sealer.atom(ans), sealer.atom(mid)
            ctx = render(sealer, edges)
            for name, handles in {
                "opaque_rel": f"""Handles:
works_at={sealer.atom('works_at')}
located_in={sealer.atom('located_in')}
Join works_at then located_in. Ignore owned_by/founded_in/partner_of. City seal only.
""",
                "none": "No handles. Sealed triples only. City seal or UNKNOWN.\n",
            }.items():
                cid = f"MOC_G{i}_{twin}_{name}"
                body = f"""OPAQUE JOIN — no decryption.
{handles}
QUESTION:
{sealer.text(q)}

CONTEXT:
{ctx}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
                path = RUNS / f"{cid}.txt"
                path.write_text("MODEL UNDER TEST. No tools. No other files.\n\n=== QUIZ ===\n" + body)
                cases.append(
                    {
                        "id": cid,
                        "condition": name,
                        "twin": twin,
                        "g": i,
                        "expect_sealed": ans_s,
                        "expect_plain": ans,
                        "intermediate_company_seal": mid_s,
                        "decoy_tails": [sealer.atom(f"HoldCo{i}"), sealer.atom(f"Year{i}A"), sealer.atom(f"Partner{i}A")],
                        "payload": str(path),
                    }
                )

    for name in ("opaque_rel", "none"):
        subset = [c for c in cases if c["condition"] == name]
        lines = ["MODEL UNDER TEST. Answer EVERY ID.\n", "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n"]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (RUNS / f"BATCH_{name}.txt").write_text("\n".join(lines))

    (RESULTS / "multi_out_confound_harness.json").write_text(
        json.dumps({"n": len(cases), "rev": sealer.rev, "cases": cases}, indent=2)
    )
    print(json.dumps({"n": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
