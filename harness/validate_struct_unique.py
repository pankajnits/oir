#!/usr/bin/env python3
"""
Deeper validation: zero-shot ID reasoning when the target relation is
STRUCTURALLY UNIQUE (information-theoretically identifiable).

Prior ZS failed with 0/4 because owned_by / located_in / partner_of were
isomorphic (all pure sinks) — so 'which 2-hop?' was undefined.

Now:
  - located_in tails = pure sinks (never heads)
  - owned_by tails = NOT sinks (Hold has outgoing edges)
  - partner_of tails = NOT sinks (Partner has outgoing edges)

Query (no English city/works/located, no handles, no demos):
  From SUBJECT, take the unique 2-hop path that ends at a node which never
  appears as a HEAD in CONTEXT. Return that end seal.

If model has real ID/structure reasoning → should PASS without few-shot.
If still fails → deeper limitation than ambiguity alone.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KEY = b"oir-validate-struct-unique-v1"


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


def graph(i: int, twin: str):
    alice = f"Alice{i}"
    acme, beta = f"Acme{i}", f"Beta{i}"
    cx, cy = f"CityX{i}", f"CityY{i}"
    hold, holdb = f"Hold{i}", f"HoldB{i}"
    part, partb = f"Part{i}", f"PartB{i}"
    # owned_by / partner tails are NOT pure sinks — they head other edges
    edges = [
        (f"Bob{i}", "works_at", beta),
        (acme, "owned_by", hold),
        (beta, "owned_by", holdb),
        (hold, "meta_of", f"Meta{i}"),      # Hold is a head → not sink
        (holdb, "meta_of", f"MetaB{i}"),
        (acme, "partner_of", part),
        (beta, "partner_of", partb),
        (part, "meta_of", f"PMeta{i}"),    # Partner is a head → not sink
        (partb, "meta_of", f"PMetaB{i}"),
        # city edges listed in middle of file (not first out-edge)
        (acme, "located_in", cx),
        (beta, "located_in", cy),
        # cities are pure sinks — never appear as heads
    ]
    if twin == "A":
        edges = [(alice, "works_at", acme)] + edges
        ans = cx
        wrong_part = part
        wrong_hold = hold
    else:
        edges = [(alice, "works_at", beta)] + edges
        ans = cy
        wrong_part = partb
        wrong_hold = holdb
    return edges, alice, ans, wrong_part, wrong_hold


def main():
    sealer = EntitySeal(KEY)
    for r in ("works_at", "located_in", "owned_by", "partner_of", "meta_of"):
        sealer.atom(r)

    cases = []
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "All tokens are opaque IDs. Same ID = same node/edge-label everywhere.\n",
        "No demos. No handles. No English relation lexicon.\n",
        "TASK: From SUBJECT, follow exactly two edges to a node that NEVER appears\n",
        "in the LEFT (head) column of CONTEXT. If several such ends exist, UNKNOWN.\n",
        "If none, UNKNOWN. Reply with that end-node seal only.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
    ]

    for i in range(4):
        for twin in ("A", "B"):
            edges, alice, ans, wp, wh = graph(i, twin)
            # verify structural uniqueness in plaintext
            heads = {h for h, r, t in edges}
            assert ans not in heads
            assert wp in heads and wh in heads

            cid = f"VALU_G{i}_{twin}"
            lines.append(
                f"""
##### ID {cid} #####
SUBJECT {sealer.atom(alice)}

CONTEXT:
{render(sealer, edges)}
"""
            )
            cases.append(
                {
                    "id": cid,
                    "expect_sealed": sealer.atom(ans),
                    "expect_plain": ans,
                    "wrong_part": sealer.atom(wp),
                    "wrong_hold": sealer.atom(wh),
                    "mid_company": sealer.atom(f"Acme{i}" if twin == "A" else f"Beta{i}"),
                }
            )

    d = ROOT / "runs" / "val_struct_unique_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    (d / "BATCH_struct_unique.txt").write_text("\n".join(lines))

    # Ambiguous control: all three company-outs are pure sinks (prior regime)
    amb_lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "All tokens are opaque IDs. Same ID = same node/edge-label.\n",
        "TASK: From SUBJECT, follow exactly two edges to a node that NEVER appears\n",
        "in the LEFT (head) column. If several such ends exist, UNKNOWN.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
    ]
    amb_cases = []
    for i in range(2):
        for twin in ("A", "B"):
            alice = f"A{i}"
            acme, beta = f"C{i}", f"D{i}"
            cx, cy = f"X{i}", f"Y{i}"
            # all sinks pure — ambiguous under the structural rule → expect UNKNOWN
            edges = [
                (alice if twin == "A" else f"Z{i}", "works_at", acme if twin == "A" else beta),
                (("Bob", "works_at", beta) if twin == "A" else (alice, "works_at", beta)),
            ]
            # simplify amb graph
            edges = [
                (alice, "works_at", acme if twin == "A" else beta),
                (f"Bob{i}", "works_at", beta if twin == "A" else acme),
                (acme, "owned_by", f"H{i}"),
                (beta, "owned_by", f"Hb{i}"),
                (acme, "partner_of", f"P{i}"),
                (beta, "partner_of", f"Pb{i}"),
                (acme, "located_in", cx),
                (beta, "located_in", cy),
            ]
            # all of H,P,X are pure sinks
            cid = f"VALA_G{i}_{twin}"
            amb_lines.append(
                f"""
##### ID {cid} #####
SUBJECT {sealer.atom(alice)}

CONTEXT:
{render(sealer, edges)}
"""
            )
            amb_cases.append(
                {
                    "id": cid,
                    "expect_sealed": "UNKNOWN",  # structurally ambiguous
                    "city": sealer.atom(cx if twin == "A" else cy),
                }
            )

    d2 = ROOT / "runs" / "val_struct_ambig_ONLY"
    d2.mkdir(parents=True, exist_ok=True)
    (d2 / "BATCH_ambig.txt").write_text("\n".join(amb_lines))

    (RESULTS / "validate_struct_unique_harness.json").write_text(
        json.dumps(
            {
                "unique": cases,
                "ambiguous": amb_cases,
                "rev": sealer.rev,
                "claim": "ZS ID reasoning works iff target relation is structurally unique",
            },
            indent=2,
        )
    )
    print(json.dumps({"unique": len(cases), "ambig": len(amb_cases)}, indent=2))


if __name__ == "__main__":
    main()
