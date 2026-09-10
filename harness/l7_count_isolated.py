#!/usr/bin/env python3
"""
L7 COUNT binder + isolated plain_relcol (clean protocol).

Novel thread: aggregation under seals — how many people work_at companies
located_in CityX? Twin flips city wiring so counts differ.

Protocol: each condition lives in its OWN directory; no sibling handle batches.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KEY = b"oir-l7-count-isolated-v1"


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


def render_sealed(sealer, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def render_plain_rel(sealer, edges):
    return "\n".join(f"{sealer.atom(h)} | {r} | {sealer.atom(t)}" for h, r, t in edges)


def write_isolated(subdir: str, name: str, body: str) -> Path:
    d = ROOT / "runs" / subdir
    d.mkdir(parents=True, exist_ok=True)
    # ensure no answer files
    for p in d.glob("README*"):
        p.unlink()
    path = d / f"{name}.txt"
    path.write_text("MODEL UNDER TEST. No tools. Read ONLY this file.\n\n=== QUIZ ===\n" + body)
    return path


def graph_count(i: int, twin: str):
    """
    People P0,P1,P2 at CoA; P3 at CoB.
    Twin A: CoA in CityX, CoB in CityY → count in CityX = 3
    Twin B: CoA in CityY, CoB in CityX → count in CityX = 1
    """
    people_a = [f"P{i}_{k}" for k in range(3)]
    person_b = f"P{i}_3"
    co_a, co_b = f"CoA{i}", f"CoB{i}"
    cx, cy = f"CityX{i}", f"CityY{i}"
    edges = [(p, "works_at", co_a) for p in people_a] + [(person_b, "works_at", co_b)]
    if twin == "A":
        edges += [(co_a, "located_in", cx), (co_b, "located_in", cy)]
        count = 3
    else:
        edges += [(co_a, "located_in", cy), (co_b, "located_in", cx)]
        count = 1
    # distractors
    edges += [
        (f"Dx{i}", "works_at", f"Dco{i}"),
        (f"Dco{i}", "located_in", f"Dcity{i}"),
        (co_a, "owned_by", f"Hold{i}"),
    ]
    return edges, cx, count


def main():
    sealer = EntitySeal(KEY)
    cases = []

    # --- L7 COUNT ---
    for i in range(4):
        for twin in ("A", "B"):
            edges, city, count = graph_count(i, twin)
            q = (
                f"How many people work_at a company that is located_in {city}? "
                f"Reply with the integer count only."
            )
            # plain
            body = f"""Answer from CONTEXT. Format: ANSWER_PLAIN: <integer>

QUESTION: {q}

CONTEXT:
{chr(10).join(f'{h} | {r} | {t}' for h,r,t in edges)}
"""
            cid = f"L7_G{i}_{twin}_plain"
            path = write_isolated(f"l7_isolated/{cid}", cid, body)
            cases.append(
                {
                    "id": cid,
                    "level": "L7",
                    "mode": "plain",
                    "twin": twin,
                    "expect": str(count),
                    "expect_sealed": str(count),
                    "payload": str(path),
                }
            )
            # handles (isolated dir per condition family)
            handles = f"""Handles:
city={sealer.atom(city)}
works_at={sealer.atom('works_at')}
located_in={sealer.atom('located_in')}
Count people whose company is located_in the target city. Integer only.
"""
            body_h = f"""OPAQUE COUNT JOIN — no decryption.
{handles}
QUESTION:
{sealer.text(q)}

CONTEXT:
{render_sealed(sealer, edges)}

Reply: ANSWER_SEALED: <integer>   (count is plaintext integer)
"""
            cid_h = f"L7_G{i}_{twin}_handles"
            path_h = write_isolated(f"l7_isolated/{cid_h}", cid_h, body_h)
            cases.append(
                {
                    "id": cid_h,
                    "level": "L7",
                    "mode": "handles",
                    "twin": twin,
                    "expect": str(count),
                    "expect_sealed": str(count),
                    "payload": str(path_h),
                }
            )

    # batches as single files but in isolated condition dirs (no sibling)
    for mode in ("plain", "handles"):
        subset = [c for c in cases if c["mode"] == mode]
        tag = "PLAIN" if mode == "plain" else "SEALED"
        lines = [
            "MODEL UNDER TEST. No tools. Read ONLY this file. Answer EVERY ID.\n",
            f"Format: ANSWER_{tag}[<id>]: <integer>\n",
        ]
        for c in subset:
            quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
        d = ROOT / "runs" / f"l7_batch_{mode}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"BATCH_L7_{mode}.txt").write_text("\n".join(lines))

    # --- Isolated plain_relcol (entities sealed, English relations) ---
    pr_cases = []
    for i in range(4):
        for twin in ("A", "B"):
            alice = f"Alice{i}"
            acme, beta = f"Acme{i}", f"Beta{i}"
            cx, cy = f"CityX{i}", f"CityY{i}"
            base = [
                (f"Bob{i}", "works_at", beta),
                (acme, "located_in", cx),
                (beta, "located_in", cy),
                (acme, "owned_by", f"Hold{i}"),
                (beta, "owned_by", f"HoldB{i}"),
            ]
            if twin == "A":
                edges = [(alice, "works_at", acme)] + base
                ans = cx
            else:
                edges = [(alice, "works_at", beta)] + base
                ans = cy
            q = f"Where is the company located that {alice} works_at? City only."
            body = f"""Entities sealed; middle column is English relation names.
Join works_at then located_in. Answer city seal only.

QUESTION:
{q.replace(alice, sealer.atom(alice))}

CONTEXT:
{render_plain_rel(sealer, edges)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
"""
            cid = f"PRC_G{i}_{twin}"
            path = write_isolated(f"plain_relcol_isolated/{cid}", cid, body)
            pr_cases.append(
                {
                    "id": cid,
                    "twin": twin,
                    "expect_plain": ans,
                    "expect_sealed": sealer.atom(ans),
                    "payload": str(path),
                }
            )

    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file. Answer EVERY ID.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
    ]
    for c in pr_cases:
        quiz = Path(c["payload"]).read_text().split("=== QUIZ ===\n", 1)[1]
        lines.append(f"\n##### ID {c['id']} #####\n{quiz}\n")
    d = ROOT / "runs" / "plain_relcol_batch_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    (d / "BATCH_plain_relcol.txt").write_text("\n".join(lines))

    harness = {
        "benchmark": "L7_count_and_isolated_plain_relcol",
        "l7": cases,
        "plain_relcol": pr_cases,
        "rev": sealer.rev,
        "protocol": "isolated condition directories; no sibling handle batches",
    }
    (RESULTS / "l7_prc_harness.json").write_text(json.dumps(harness, indent=2))
    print(
        json.dumps(
            {
                "l7": len(cases),
                "prc": len(pr_cases),
                "batches": [
                    "runs/l7_batch_plain_ONLY/",
                    "runs/l7_batch_handles_ONLY/",
                    "runs/plain_relcol_batch_ONLY/",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
