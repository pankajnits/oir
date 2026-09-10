#!/usr/bin/env python3
"""
Second OOD relation family + symbolic seal-router baseline.

A. Behavioral: stationed_in (another held-out city relation) — handles vs nohandle.
B. Symbolic SealRouter: exact graph executor over seals — upper bound / reference
   for what Intervention-1 should approximate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KEY = b"oir-ood2-sealrouter-v1"


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


class SealRouter:
    """Exact symbolic executor: follow (head_seal, rel_seal) → tail_seal."""

    def __init__(self, triples: list[tuple[str, str, str]]):
        self.index: dict[tuple[str, str], list[str]] = {}
        for h, r, t in triples:
            self.index.setdefault((h, r), []).append(t)

    def step(self, head: str, rel: str) -> list[str]:
        return list(self.index.get((head, rel), []))

    def path(self, start: str, rels: list[str]) -> list[str]:
        frontier = [start]
        for rel in rels:
            nxt = []
            for h in frontier:
                nxt.extend(self.step(h, rel))
            frontier = nxt
        return frontier

    def count_path(self, starts: list[str], rels: list[str], target_tail: str | None = None) -> int:
        n = 0
        for s in starts:
            ends = self.path(s, rels)
            if target_tail is None:
                n += len(ends)
            else:
                n += sum(1 for e in ends if e == target_tail)
        return n


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
    return edges, alice, ans


def main():
    sealer = EntitySeal(KEY)
    cases = []
    router_checks = []

    for i in range(4):
        for twin in ("A", "B"):
            edges, alice, ans = graph(i, twin, "stationed_in")
            q = f"What city is associated with the employer of {sealer.atom(alice)}? City seal only."
            sealed_triples = [(sealer.atom(h), sealer.atom(r), sealer.atom(t)) for h, r, t in edges]
            router = SealRouter(sealed_triples)
            predicted = router.path(sealer.atom(alice), [sealer.atom("works_at"), sealer.atom("stationed_in")])
            assert predicted == [sealer.atom(ans)], (predicted, ans)
            router_checks.append({"id": f"G{i}_{twin}", "router": predicted[0], "expect": sealer.atom(ans)})

            for cond, handles in {
                "ood2_handles": f"""Handles (fresh city relation stationed_in):
employer_rel={sealer.atom('works_at')}
city_rel={sealer.atom('stationed_in')}
Join person-employer_rel→co ; co-city_rel→city.
""",
                "ood2_nohandle": """English plan only (no seal bindings): join works_at then stationed_in.
All CONTEXT atoms are opaque seals.
""",
            }.items():
                cid = f"OOD2_G{i}_{twin}_{cond}"
                body = f"""OPAQUE JOIN — no decryption.
{handles}
QUESTION:
{q}

CONTEXT:
{render(sealer, edges)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
                d = ROOT / "runs" / f"{cond}_ONLY"
                d.mkdir(parents=True, exist_ok=True)
                path = d / f"{cid}.txt"
                path.write_text("MODEL UNDER TEST. No tools. Read ONLY this file.\n\n=== QUIZ ===\n" + body)
                cases.append(
                    {
                        "id": cid,
                        "condition": cond,
                        "expect_sealed": sealer.atom(ans),
                        "expect_plain": ans,
                        "payload": str(path),
                    }
                )

    for cond in ("ood2_handles", "ood2_nohandle"):
        subset = [c for c in cases if c["condition"] == cond]
        d = ROOT / "runs" / f"{cond}_ONLY"
        lines = [
            "MODEL UNDER TEST. No tools. Read ONLY this file. Answer EVERY ID.\n",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        (d / f"BATCH_{cond}.txt").write_text("\n".join(lines))

    # Standalone sealrouter demo on L7-like count
    demo_edges = []
    for k in range(3):
        demo_edges.append((f"P{k}", "works_at", "CoA"))
    demo_edges += [("P3", "works_at", "CoB"), ("CoA", "located_in", "CityX"), ("CoB", "located_in", "CityY")]
    st = [(sealer.atom(h), sealer.atom(r), sealer.atom(t)) for h, r, t in demo_edges]
    r = SealRouter(st)
    people = [sealer.atom(f"P{k}") for k in range(4)]
    # count people whose path works_at→located_in ends at CityX
    cnt = 0
    for p in people:
        ends = r.path(p, [sealer.atom("works_at"), sealer.atom("located_in")])
        cnt += sum(1 for e in ends if e == sealer.atom("CityX"))

    harness = {
        "benchmark": "ood2_stationed_in + SealRouter baseline",
        "router_checks": router_checks,
        "router_count_demo": {"CityX_count": cnt, "expect": 3},
        "n": len(cases),
        "rev": sealer.rev,
        "cases": cases,
    }
    (RESULTS / "ood2_sealrouter_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": len(cases), "router_all_ok": all(c["router"] == c["expect"] for c in router_checks), "count_demo": cnt}, indent=2))


if __name__ == "__main__":
    main()
