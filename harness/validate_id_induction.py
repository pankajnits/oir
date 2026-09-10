#!/usr/bin/env python3
"""
Validate: can the model induce relation roles from IDs alone?

User hypothesis: if a model reasons on IDs, it can figure out relations on IDs
automatically (no English handles).

Tests (isolated dirs, multi-out edges, owned_by BEFORE city, no relation words in Q):

  ZS  — zero-shot: sealed graph + sealed person only. No handles, no demos.
  FS  — few-shot: 2 fully worked sealed demos (same relation seals!), then query.
        If model induces which middle seals are hop1/hop2 from demos → PASS.
  FS_SHUFFLE — few-shot but EACH demo uses a DIFFERENT key's seals... no, same key.
        Better: few-shot with SAME seals for relations across demos (shared schema).

Prediction if user right: FS >> ZS.
Prediction if our claim right: both fail OR only FS passes (induction needs demos,
  still not "from a single opaque graph alone").
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
KEY = b"oir-validate-id-induction-v1"


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
    # owned_by before city; shuffle people order slightly by construction
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def graph(i: int, twin: str, city_rel: str = "located_in"):
    alice = f"Alice{i}"
    acme, beta = f"Acme{i}", f"Beta{i}"
    cx, cy = f"CityX{i}", f"CityY{i}"
    edges = [
        (f"Bob{i}", "works_at", beta),
        (acme, "owned_by", f"Hold{i}"),
        (beta, "owned_by", f"HoldB{i}"),
        (acme, city_rel, cx),
        (beta, city_rel, cy),
        (acme, "partner_of", f"Part{i}"),
        (beta, "partner_of", f"PartB{i}"),
    ]
    if twin == "A":
        edges = [(alice, "works_at", acme)] + edges
        ans = cx
    else:
        edges = [(alice, "works_at", beta)] + edges
        ans = cy
    return edges, alice, ans


def demo_block(sealer, i: int, twin: str) -> tuple[str, str]:
    """Worked example: show question person seal and answer city seal with context."""
    edges, alice, ans = graph(i, twin)
    q = f"SUBJECT {sealer.atom(alice)}\nReturn the 2-hop city seal (employer then city-rel). One seal only."
    body = f"""DEMO:
{q}

CONTEXT:
{render(sealer, edges)}

ANSWER_SEALED: {sealer.atom(ans)}
"""
    return body, ans


def main():
    sealer = EntitySeal(KEY)
    # Warm schema seals once so demos and queries share relation seals
    for r in ("works_at", "located_in", "owned_by", "partner_of"):
        sealer.atom(r)

    cases = []

    # --- Zero-shot batch: queries G2,G3 only (G0,G1 reserved for demos in FS) ---
    zs_lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "All tokens are opaque IDs. Same ID = same entity/relation.\n",
        "No English relation names. No handles.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
    ]
    for i in (2, 3):
        for twin in ("A", "B"):
            edges, alice, ans = graph(i, twin)
            cid = f"VAL_ZS_G{i}_{twin}"
            zs_lines.append(
                f"""
##### ID {cid} #####
SUBJECT {sealer.atom(alice)}
Return the 2-hop city seal. One seal or UNKNOWN.

CONTEXT:
{render(sealer, edges)}
"""
            )
            cases.append(
                {
                    "id": cid,
                    "cond": "zero_shot",
                    "expect_sealed": sealer.atom(ans),
                    "expect_plain": ans,
                    "hold": sealer.atom(f"Hold{i}" if twin == "A" else f"HoldB{i}"),
                }
            )

    d_zs = ROOT / "runs" / "val_zs_ONLY"
    d_zs.mkdir(parents=True, exist_ok=True)
    (d_zs / "BATCH_zs.txt").write_text("\n".join(zs_lines))

    # --- Few-shot: demos G0_A, G0_B, G1_A then query G2/G3 ---
    fs_lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "All tokens are opaque IDs. Same ID = same entity/relation across demos and quiz.\n",
        "Relation seals are SHARED across demos. Induce which middle seals are the 2-hop path from demos.\n",
        "No English relation names. No handles.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n\n=== DEMOS ===\n",
    ]
    for i, twin in [(0, "A"), (0, "B"), (1, "A")]:
        block, _ = demo_block(sealer, i, twin)
        fs_lines.append(block + "\n")

    fs_lines.append("\n=== QUIZ ===\n")
    for i in (2, 3):
        for twin in ("A", "B"):
            edges, alice, ans = graph(i, twin)
            cid = f"VAL_FS_G{i}_{twin}"
            fs_lines.append(
                f"""
##### ID {cid} #####
SUBJECT {sealer.atom(alice)}
Return the 2-hop city seal (same path type as demos). One seal or UNKNOWN.

CONTEXT:
{render(sealer, edges)}
"""
            )
            cases.append(
                {
                    "id": cid,
                    "cond": "few_shot",
                    "expect_sealed": sealer.atom(ans),
                    "expect_plain": ans,
                    "hold": sealer.atom(f"Hold{i}" if twin == "A" else f"HoldB{i}"),
                }
            )

    d_fs = ROOT / "runs" / "val_fs_ONLY"
    d_fs.mkdir(parents=True, exist_ok=True)
    (d_fs / "BATCH_fs.txt").write_text("\n".join(fs_lines))

    # --- Control: few-shot WITH explicit sealed relation handles (should pass) ---
    fh_lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        f"Handles: hop1={sealer.atom('works_at')} hop2={sealer.atom('located_in')}\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
    ]
    for i in (2, 3):
        for twin in ("A", "B"):
            edges, alice, ans = graph(i, twin)
            cid = f"VAL_FH_G{i}_{twin}"
            fh_lines.append(
                f"""
##### ID {cid} #####
SUBJECT {sealer.atom(alice)}
Join hop1 then hop2. City seal only.

CONTEXT:
{render(sealer, edges)}
"""
            )
            cases.append(
                {
                    "id": cid,
                    "cond": "few_shot_handles",  # actually zero-shot + handles
                    "expect_sealed": sealer.atom(ans),
                    "expect_plain": ans,
                    "hold": sealer.atom(f"Hold{i}" if twin == "A" else f"HoldB{i}"),
                }
            )

    d_fh = ROOT / "runs" / "val_fh_ONLY"
    d_fh.mkdir(parents=True, exist_ok=True)
    (d_fh / "BATCH_fh.txt").write_text("\n".join(fh_lines))

    (RESULTS / "validate_id_induction_harness.json").write_text(
        json.dumps(
            {
                "hypothesis": "Model can induce relation roles from IDs alone",
                "n": len(cases),
                "rev": sealer.rev,
                "cases": cases,
                "shared_relation_seals": {
                    "works_at": sealer.atom("works_at"),
                    "located_in": sealer.atom("located_in"),
                    "owned_by": sealer.atom("owned_by"),
                    "partner_of": sealer.atom("partner_of"),
                },
            },
            indent=2,
        )
    )
    print(json.dumps({"zs": 4, "fs": 4, "fh": 4}, indent=2))


if __name__ == "__main__":
    main()
