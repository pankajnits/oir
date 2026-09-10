#!/usr/bin/env python3
"""
English relation-label control (scrutiny).

Competing explanations for why handles work:
  H1: opaque relation *seals* ground equality matching in seal space
  H2: English relation *words* in the handle block leak the plan (works_at → located_in)

Controls on the same 8 twin graphs (as partial_scaled):
  opaque_rel  — works_at=<seal> located_in=<seal>   (baseline = rel_only)
  english_rel — works_at / located_in as plaintext words; entities remain sealed
  mixed       — English relation words + opaque person seal
  schema_only — "Join works_at then located_in" in English; NO seal bindings at all

If english_rel ≈ opaque_rel, H2 is plausible (plan leak).
If english_rel << opaque_rel, H1 is supported (need seal-space relation grounding).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "english_rel_control"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)

KEY = b"oir-english-rel-control-v1"


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


def render(sealer: EntitySeal, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def graph_i(i: int, twin: str):
    alice, bob, carol = f"Alice{i}", f"Bob{i}", f"Carol{i}"
    acme, beta = f"Acme{i}", f"Beta{i}"
    cx, cy = f"CityX{i}", f"CityY{i}"
    base = [
        (bob, "works_at", beta),
        (carol, "works_at", acme),
        (carol, "reports_to", bob),
        (acme, "located_in", cx),
        (beta, "located_in", cy),
    ]
    if twin == "A":
        edges = [(alice, "works_at", acme)] + base
        ans, mid = cx, acme
    else:
        edges = [(alice, "works_at", beta)] + base
        ans, mid = cy, beta
    return edges, alice, ans, mid


def main():
    sealer = EntitySeal(KEY)
    cases = []
    for i in range(8):
        for twin in ("A", "B"):
            edges, alice, ans, mid = graph_i(i, twin)
            ctx = render(sealer, edges)
            q = f"Where is the company located that {alice} works_at? City only."
            ans_s, mid_s = sealer.atom(ans), sealer.atom(mid)
            variants = {
                "opaque_rel": f"""Handles (opaque relations):
works_at={sealer.atom('works_at')}
located_in={sealer.atom('located_in')}
Subject sealed in QUESTION. Join works_at then located_in. City seal only.
""",
                "english_rel": f"""Handles (English relation words — not seals):
Relation names in CONTEXT middle column mean works_at and located_in in English.
You must still match the *sealed* middle tokens that correspond to those roles.
Join: follow works_at then located_in. City seal only.
(Note: CONTEXT shows sealed tokens for ALL columns including relations.)
""",
                "mixed": f"""Handles:
person={sealer.atom(alice)}
English plan: join works_at then located_in (relation words are English, not seals).
City seal only.
""",
                "schema_only": """English plan only (no seal bindings):
Find the subject's works_at company, then that company's located_in city.
All atoms in CONTEXT are opaque seals. City seal or UNKNOWN.
""",
            }
            for name, handles in variants.items():
                cid = f"ERC_G{i}_{twin}_{name}"
                body = f"""OPAQUE JOIN — no decryption. Same entity ⇒ same seal.
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
                        "g": i,
                        "twin": twin,
                        "condition": name,
                        "expect_plain": ans,
                        "expect_sealed": ans_s,
                        "intermediate_company_seal": mid_s,
                        "payload": str(path),
                    }
                )

    for name in ("opaque_rel", "english_rel", "mixed", "schema_only"):
        subset = [c for c in cases if c["condition"] == name]
        lines = [
            "MODEL UNDER TEST. No tools. Answer EVERY ID.\n",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (RUNS / f"BATCH_{name}.txt").write_text("\n".join(lines))

    harness = {
        "benchmark": "english_relation_control",
        "hypothesis": "H1 opaque relation seals vs H2 English plan leak",
        "n": len(cases),
        "rev": sealer.rev,
        "cases": cases,
    }
    (RESULTS / "english_rel_control_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": len(cases), "batches": 4}, indent=2))


if __name__ == "__main__":
    main()
