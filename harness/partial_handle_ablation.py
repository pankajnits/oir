#!/usr/bin/env python3
"""
Partial-handle ablation (novelty / mechanism probe).

Hypothesis: SEAL-Join success is driven by opaque *relation* handles that
label which edge type to follow — not by English question wording alone.

Ablations on the same twin graph (Alice city):
  full     — person + works_at + located_in handles (baseline)
  rel_only — relation seals only (works_at, located_in); person in sealed question
  person_only — person handle only; relations must be inferred from structure
  none     — sealed context + sealed question; no handle block (≈ nohint)

If rel_only ≈ full and person_only/none collapse to intermediate-company errors,
that supports: relation-type grounding is the critical scaffold for OIR joins.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "partial_handles"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)

KEY = b"oir-partial-handle-ablation-v1"


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


def edges_twin(twin: str):
    # Same bag, different Alice employer wiring (classic SEAL-Join twin).
    base = [
        ("Bob", "works_at", "BetaCorp"),
        ("Carol", "works_at", "Acme"),
        ("Carol", "reports_to", "Bob"),
        ("Acme", "located_in", "CityX"),
        ("BetaCorp", "located_in", "CityY"),
    ]
    if twin == "A":
        return [("Alice", "works_at", "Acme")] + base
    return [("Alice", "works_at", "BetaCorp")] + base


def render(sealer: EntitySeal, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def make():
    sealer = EntitySeal(KEY)
    q_en = "Where is the company located that Alice works_at? City only."
    expect = {"A": "CityX", "B": "CityY"}
    cases = []

    for twin in ("A", "B"):
        edges = edges_twin(twin)
        ctx = render(sealer, edges)
        ans = expect[twin]
        ans_s = sealer.atom(ans)
        intermed = sealer.atom("Acme" if twin == "A" else "BetaCorp")

        variants = {
            "full": f"""Handles (opaque):
person={sealer.atom('Alice')}
works_at={sealer.atom('works_at')}
located_in={sealer.atom('located_in')}
Join: person-works_at→co ; co-located_in→city. Answer city seal only.
""",
            "rel_only": f"""Handles (relations only):
works_at={sealer.atom('works_at')}
located_in={sealer.atom('located_in')}
Subject of question is sealed in QUESTION. Join works_at then located_in. City seal only.
""",
            "person_only": f"""Handles (person only):
person={sealer.atom('Alice')}
No relation seals given. Infer which middle token is the relation from triple structure.
Join to city. City seal only.
""",
            "none": """No handles. Sealed triples only. Answer city seal or UNKNOWN.
""",
        }

        for name, handles in variants.items():
            cid = f"PH_{twin}_{name}"
            body = f"""OPAQUE JOIN — no decryption. Same entity ⇒ same seal.
{handles}
QUESTION:
{sealer.text(q_en)}

CONTEXT:
{ctx}

Reply ONE line: ANSWER_SEALED: <seal> OR UNKNOWN
"""
            path = RUNS / f"{cid}.txt"
            path.write_text("MODEL UNDER TEST. No tools. No other files.\n\n=== QUIZ ===\n" + body)
            cases.append(
                {
                    "id": cid,
                    "twin": twin,
                    "ablation": name,
                    "expect_plain": ans,
                    "expect_sealed": ans_s,
                    "intermediate_company_seal": intermed,
                    "payload": str(path),
                }
            )

    # Batches by ablation (both twins)
    for name in ("full", "rel_only", "person_only", "none"):
        subset = [c for c in cases if c["ablation"] == name]
        lines = [
            "MODEL UNDER TEST. No tools. Answer EVERY ID.\n",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (RUNS / f"BATCH_{name}.txt").write_text("\n".join(lines))

    harness = {
        "benchmark": "partial_handle_ablation",
        "hypothesis": "relation handles are necessary/sufficient scaffold for 2-hop OIR join",
        "rev": sealer.rev,
        "cases": cases,
    }
    (RESULTS / "partial_handle_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": len(cases), "batches": 4}, indent=2))
    return harness


if __name__ == "__main__":
    make()
