#!/usr/bin/env python3
"""
No-relation-crib control.

Confound: sealing the English question leaks σ(works_at) because the word
appears in the question. Clean control seals ONLY the person atom in the
question; relation words are replaced by underspecified language
("employer" / "city of that employer") so no relation seal is cribbed.

Predict: with opaque_rel handles → PASS; with none → FAIL (intermediate).
Isolated directories.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KEY = b"oir-no-rel-crib-v1"


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


def main():
    sealer = EntitySeal(KEY)
    cases = []
    for i in range(4):
        for twin in ("A", "B"):
            alice = f"Alice{i}"
            acme, beta = f"Acme{i}", f"Beta{i}"
            cx, cy = f"CityX{i}", f"CityY{i}"
            edges = [
                (f"Bob{i}", "works_at", beta),
                (acme, "located_in", cx),
                (beta, "located_in", cy),
                (acme, "owned_by", f"Hold{i}"),
                (beta, "owned_by", f"HoldB{i}"),
            ]
            if twin == "A":
                edges = [(alice, "works_at", acme)] + edges
                ans = cx
            else:
                edges = [(alice, "works_at", beta)] + edges
                ans = cy
            # Question: NO works_at / located_in tokens
            q = f"What city is associated with the employer of {sealer.atom(alice)}? Reply city seal only."
            ctx = render(sealer, edges)
            for name, handles in {
                "opaque_rel": f"""Handles:
employer_rel={sealer.atom('works_at')}
city_rel={sealer.atom('located_in')}
Join person -employer_rel→ co -city_rel→ city.
""",
                "none": "No handles. Sealed triples only.\n",
            }.items():
                cid = f"NRC_G{i}_{twin}_{name}"
                body = f"""OPAQUE JOIN — no decryption.
{handles}
QUESTION:
{q}

CONTEXT:
{ctx}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
                d = ROOT / "runs" / f"nrc_{name}_ONLY"
                d.mkdir(parents=True, exist_ok=True)
                path = d / f"{cid}.txt"
                path.write_text("MODEL UNDER TEST. No tools. Read ONLY this file.\n\n=== QUIZ ===\n" + body)
                cases.append(
                    {
                        "id": cid,
                        "condition": name,
                        "twin": twin,
                        "expect_sealed": sealer.atom(ans),
                        "expect_plain": ans,
                        "mid": sealer.atom(acme if twin == "A" else beta),
                        "payload": str(path),
                    }
                )

    for name in ("opaque_rel", "none"):
        subset = [c for c in cases if c["condition"] == name]
        d = ROOT / "runs" / f"nrc_{name}_ONLY"
        lines = [
            "MODEL UNDER TEST. No tools. Read ONLY this file. Answer EVERY ID.\n",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (d / f"BATCH_{name}.txt").write_text("\n".join(lines))

    (RESULTS / "no_rel_crib_harness.json").write_text(
        json.dumps({"n": len(cases), "rev": sealer.rev, "cases": cases}, indent=2)
    )
    print(json.dumps({"n": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
