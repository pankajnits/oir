#!/usr/bin/env python3
"""
Scaled partial-handle ablation + L6 negation binder.

A. Scale PH: 8 twin graphs × 4 ablations = 64 sealed cases (batches by ablation).
B. L6: anti-join / negation — city of Alice's company that is NOT Bob's city.
   Twin flips wiring so answers differ; requires binder + negation under seals.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_PH = ROOT / "runs" / "partial_handles_scaled"
RUNS_L6 = ROOT / "runs" / "seal_bench_l6"
RESULTS = ROOT / "results"
RUNS_PH.mkdir(parents=True, exist_ok=True)
RUNS_L6.mkdir(parents=True, exist_ok=True)

KEY = b"oir-partial-scaled-l6-v1"


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
    return edges, alice, ans, mid, cx, cy, bob


def make_partial_scaled(sealer: EntitySeal):
    cases = []
    for i in range(8):
        for twin in ("A", "B"):
            edges, alice, ans, mid, cx, cy, bob = graph_i(i, twin)
            ctx = render(sealer, edges)
            q = f"Where is the company located that {alice} works_at? City only."
            ans_s, mid_s = sealer.atom(ans), sealer.atom(mid)
            variants = {
                "full": f"""Handles:
person={sealer.atom(alice)}
works_at={sealer.atom('works_at')}
located_in={sealer.atom('located_in')}
Join person-works_at→co ; co-located_in→city.
""",
                "rel_only": f"""Handles (relations only):
works_at={sealer.atom('works_at')}
located_in={sealer.atom('located_in')}
Subject sealed in QUESTION. Join works_at then located_in.
""",
                "person_only": f"""Handles (person only):
person={sealer.atom(alice)}
No relation seals. Infer relations from triple structure; join to city.
""",
                "none": "No handles. Sealed triples only. City seal or UNKNOWN.\n",
            }
            for name, handles in variants.items():
                cid = f"PHS_G{i}_{twin}_{name}"
                body = f"""OPAQUE JOIN — no decryption. Same entity ⇒ same seal.
{handles}
QUESTION:
{sealer.text(q)}

CONTEXT:
{ctx}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
                path = RUNS_PH / f"{cid}.txt"
                path.write_text("MODEL UNDER TEST. No tools. No other files.\n\n=== QUIZ ===\n" + body)
                cases.append(
                    {
                        "id": cid,
                        "g": i,
                        "twin": twin,
                        "ablation": name,
                        "expect_plain": ans,
                        "expect_sealed": ans_s,
                        "intermediate_company_seal": mid_s,
                        "payload": str(path),
                    }
                )

    for name in ("full", "rel_only", "person_only", "none"):
        subset = [c for c in cases if c["ablation"] == name]
        lines = [
            "MODEL UNDER TEST. No tools. Answer EVERY ID.\n",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (RUNS_PH / f"BATCH_{name}.txt").write_text("\n".join(lines))

    return cases


def make_l6(sealer: EntitySeal):
    """Negation binder: Alice's city that is NOT Bob's city (should equal Alice's city when distinct)."""
    cases = []
    for i in range(4):
        for twin in ("A", "B"):
            edges, alice, ans, mid, cx, cy, bob = graph_i(i, twin)
            # Bob always at Beta → CityY; Alice A→CityX, B→CityY.
            # Question: city of Alice's co that is NOT located_in of Bob's co.
            # Twin A: Alice CityX ≠ Bob CityY → CityX
            # Twin B: Alice CityY == Bob CityY → UNKNOWN (no city satisfying inequality)
            if twin == "A":
                expect, expect_s = cx, sealer.atom(cx)
            else:
                expect, expect_s = "UNKNOWN", "UNKNOWN"
            q = (
                f"Find the city of the company where {alice} works_at, but ONLY if that city "
                f"is NOT the city where {bob}'s company is located_in. Else UNKNOWN."
            )
            for mode in ("plain", "handles"):
                cid = f"L6_G{i}_{twin}_{mode}"
                if mode == "plain":
                    body = f"""Answer from CONTEXT. One line: ANSWER_PLAIN: <city_or_UNKNOWN>

QUESTION: {q}

CONTEXT:
{chr(10).join(f'{h} | {r} | {t}' for h,r,t in edges)}
"""
                    exp_field = expect
                else:
                    handles = f"""Handles:
A={sealer.atom(alice)} B={sealer.atom(bob)}
works_at={sealer.atom('works_at')} located_in={sealer.atom('located_in')}
Compute city_A and city_B; if city_A != city_B return city_A else UNKNOWN.
"""
                    body = f"""OPAQUE JOIN — no decryption.
{handles}
QUESTION:
{sealer.text(q)}

CONTEXT:
{render(sealer, edges)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
                    exp_field = expect_s
                path = RUNS_L6 / f"{cid}.txt"
                path.write_text("MODEL UNDER TEST. No tools. No other files.\n\n=== QUIZ ===\n" + body)
                cases.append(
                    {
                        "id": cid,
                        "level": "L6",
                        "g": i,
                        "twin": twin,
                        "mode": mode,
                        "expect": expect,
                        "expect_sealed": expect_s,
                        "payload": str(path),
                    }
                )

    for mode in ("plain", "handles"):
        subset = [c for c in cases if c["mode"] == mode]
        tag = "PLAIN" if mode == "plain" else "SEALED"
        lines = [
            "MODEL UNDER TEST. No tools. Answer EVERY ID.\n",
            f"Format: ANSWER_{tag}[<id>]: <city_or_UNKNOWN>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (RUNS_L6 / f"BATCH_L6_{mode}.txt").write_text("\n".join(lines))
    return cases


def main():
    sealer = EntitySeal(KEY)
    ph = make_partial_scaled(sealer)
    l6 = make_l6(sealer)
    harness = {
        "partial_scaled": {"n": len(ph), "cases": ph},
        "l6": {"n": len(l6), "cases": l6},
        "rev": sealer.rev,
    }
    (RESULTS / "partial_scaled_l6_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"partial_scaled": len(ph), "l6": len(l6)}, indent=2))


if __name__ == "__main__":
    main()
