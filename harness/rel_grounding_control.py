#!/usr/bin/env python3
"""
Relation grounding controls (scrutiny) — clean design.

Four conditions on identical twin graphs (8×2):

1. opaque_rel   — all columns sealed; opaque relation seal handles (OIR baseline)
2. plain_relcol — entity seals only; middle column LEFT IN ENGLISH (works_at/…)
                  Industrial-like: vault tokens for values, schema in clear.
3. schema_only  — all sealed; English join plan; no seal bindings
4. none         — all sealed; no plan text beyond question

Predictions:
- If plain_relcol ≈ opaque_rel ≫ schema_only: typed English schema is enough;
  opacity of *entities* still allows joins (weaker OIR claim, strong practice note).
- If opaque_rel ≫ plain_relcol: unlikely (English should help).
- If schema_only fails: English plan without seal grounding is insufficient.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "rel_grounding_control"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)

KEY = b"oir-rel-grounding-control-v1"


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


def render_all_sealed(sealer: EntitySeal, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def render_plain_relcol(sealer: EntitySeal, edges):
    """Seal endpoints only; keep relation label in English."""
    return "\n".join(f"{sealer.atom(h)} | {r} | {sealer.atom(t)}" for h, r, t in edges)


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
            q = f"Where is the company located that {alice} works_at? City only."
            ans_s, mid_s = sealer.atom(ans), sealer.atom(mid)

            conds = {
                "opaque_rel": {
                    "handles": f"""Handles (opaque relations):
works_at={sealer.atom('works_at')}
located_in={sealer.atom('located_in')}
Join works_at then located_in. Answer city seal only.
""",
                    "ctx": render_all_sealed(sealer, edges),
                    "q": sealer.text(q),
                },
                "plain_relcol": {
                    "handles": """Entities are sealed; relation names in the middle column are English.
Join works_at then located_in. Answer city seal only.
""",
                    "ctx": render_plain_relcol(sealer, edges),
                    # Keep English relation words in the question; only seal the person atom.
                    "q": q.replace(alice, sealer.atom(alice)),
                },
                "schema_only": {
                    "handles": """English plan only (no seal bindings):
Join works_at then located_in over sealed triples. City seal or UNKNOWN.
""",
                    "ctx": render_all_sealed(sealer, edges),
                    "q": sealer.text(q),
                },
                "none": {
                    "handles": "No handles. Sealed triples only. City seal or UNKNOWN.\n",
                    "ctx": render_all_sealed(sealer, edges),
                    "q": sealer.text(q),
                },
            }

            for name, cfg in conds.items():
                cid = f"RGC_G{i}_{twin}_{name}"
                body = f"""OPAQUE JOIN — no decryption of entities. Same entity ⇒ same seal.
{cfg['handles']}
QUESTION:
{cfg['q']}

CONTEXT:
{cfg['ctx']}

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

    for name in ("opaque_rel", "plain_relcol", "schema_only", "none"):
        subset = [c for c in cases if c["condition"] == name]
        lines = [
            "MODEL UNDER TEST. No tools. Answer EVERY ID.\n",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (RUNS / f"BATCH_{name}.txt").write_text("\n".join(lines))

    (RESULTS / "rel_grounding_harness.json").write_text(
        json.dumps(
            {
                "benchmark": "relation_grounding_control",
                "n": len(cases),
                "rev": sealer.rev,
                "cases": cases,
            },
            indent=2,
        )
    )
    print(json.dumps({"n": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
