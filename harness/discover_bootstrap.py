#!/usr/bin/env python3
"""
Discovery probe: human-like schema bootstrap.

Humans rarely get demos or handle tables. They glance at data, ask a simple
probe ("which column is the leaf?"), then answer the hard question.

Protocol (isolated):
  BOOT — Turn1: structural probe that reveals which seal is the pure-sink
          relation (no English city). Turn2: semantic-ish ask using only
          SUBJECT + 'end of the same kind of 2-hop as the unique sink path'
          on a NEW twin graph sharing relation seals.
  Compare to cold semantic fail mode conceptually.

Actually cleaner discovery:
  Single prompt with TWO graphs sharing relation seals:
    Graph P (probe): structurally unique — model must return the 2-hop sink seal
    Graph Q (query): AMBIGUOUS sinks (like earlier fail) BUT instruction says
      'use the SAME middle-edge seal type you used in Graph P'
  If PASS: model transfers induced relation ID from probe→query without English
  handles or few-shot answer demos — human-like 'look at this sheet first'.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KEY = b"oir-discover-bootstrap-v1"


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


def R(sealer, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def unique_graph(sealer, tag: str, twin: str):
    alice, bob = f"UAlice{tag}", f"UBob{tag}"
    acme, beta = f"UAcme{tag}", f"UBeta{tag}"
    cx, cy = f"UCity{tag}X", f"UCity{tag}Y"
    hold, part = f"UHold{tag}", f"UPart{tag}"
    edges = [
        (bob, "works_at", beta),
        (acme, "owned_by", hold),
        (hold, "meta_of", f"UMeta{tag}"),
        (acme, "partner_of", part),
        (part, "meta_of", f"UPMeta{tag}"),
        (beta, "owned_by", f"UHoldB{tag}"),
        (f"UHoldB{tag}", "meta_of", f"UMetaB{tag}"),
        (beta, "partner_of", f"UPartB{tag}"),
        (f"UPartB{tag}", "meta_of", f"UPMetaB{tag}"),
        (acme, "located_in", cx),
        (beta, "located_in", cy),
    ]
    if twin == "A":
        edges = [(alice, "works_at", acme)] + edges
        ans = cx
    else:
        edges = [(alice, "works_at", beta)] + edges
        ans = cy
    return edges, alice, ans


def ambig_graph(sealer, tag: str, twin: str):
    """All company outs are pure sinks — cold ZS would be ambiguous."""
    alice, bob = f"AAlice{tag}", f"ABob{tag}"
    acme, beta = f"AAcme{tag}", f"ABeta{tag}"
    cx, cy = f"ACity{tag}X", f"ACity{tag}Y"
    edges = [
        (bob, "works_at", beta),
        (acme, "owned_by", f"AH{tag}"),
        (beta, "owned_by", f"AHb{tag}"),
        (acme, "partner_of", f"AP{tag}"),
        (beta, "partner_of", f"APb{tag}"),
        (acme, "located_in", cx),
        (beta, "located_in", cy),
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
    for r in ("works_at", "located_in", "owned_by", "partner_of", "meta_of"):
        sealer.atom(r)

    cases = []
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "Opaque IDs only. Same ID = same node/relation across BOTH graphs below.\n",
        "No English relation names. No handle table. No answer demos.\n\n",
        "PROCEDURE (human-like):\n",
        "1) On GRAPH_P, from SUBJECT_P take the unique 2-hop ending at a node that\n",
        "   never appears as a LEFT/head column entry. Note which MIDDLE seal you used\n",
        "   on the second hop.\n",
        "2) On GRAPH_Q (may have several pure-sink outs), from SUBJECT_Q take 2 hops\n",
        "   using that SAME second-hop middle seal type. Return GRAPH_Q end seal.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
    ]

    for i in range(4):
        for twin in ("A", "B"):
            ep, ap, ansp = unique_graph(sealer, f"{i}p", twin)
            eq, aq, ansq = ambig_graph(sealer, f"{i}q", twin)
            # Ensure shared relation seals: same string atoms works_at/located_in etc.
            cid = f"BOOT_G{i}_{twin}"
            lines.append(
                f"""
##### ID {cid} #####
SUBJECT_P {sealer.atom(ap)}
GRAPH_P:
{R(sealer, ep)}

SUBJECT_Q {sealer.atom(aq)}
GRAPH_Q:
{R(sealer, eq)}
"""
            )
            cases.append(
                {
                    "id": cid,
                    "expect_q": sealer.atom(ansq),
                    "expect_p": sealer.atom(ansp),
                    "located_in": sealer.atom("located_in"),
                    "partner_of": sealer.atom("partner_of"),
                    "owned_by": sealer.atom("owned_by"),
                }
            )

    d = ROOT / "runs" / "discover_bootstrap_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    (d / "BATCH_boot.txt").write_text("\n".join(lines))
    (RESULTS / "discover_bootstrap_harness.json").write_text(
        json.dumps({"n": len(cases), "cases": cases, "rev": sealer.rev}, indent=2)
    )
    print(json.dumps({"n": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
