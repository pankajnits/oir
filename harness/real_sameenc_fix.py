#!/usr/bin/env python3
"""
FIX for real-data CANON failure (stopped at company 0/8).

Same-encoding only: sealed path-program question form
  START=<person> ; R1=<works_at> ; R2=<headquartered_in> ; RETURN tail after R1 then R2

No English handles legend. No plaintext. Fix = clearer sealed query syntax.
Also: sealed chain scaffold (two lines, still same encoding).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data/real/wikidata_ceo_hops.json").read_text())
RESULTS = ROOT / "results"
KEY = b"oir-real-sameenc-v1"  # SAME key as real_sameenc for comparable atoms
SEED = 20260724


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


def build_graph(row, all_rows, rng):
    person, company, hq = row["person"], row["company"], row["hq"]
    others = [r for r in all_rows if r["company"] != company]
    decoy = rng.choice(others) if others else row
    dco, dhq = decoy["company"], decoy["hq"]
    hold, part = f"Hold_{company}", f"Part_{company}"
    edges = [
        (person, "works_at", company),
        (company, "headquartered_in", hq),
        (dco, "headquartered_in", dhq),
        (company, "owned_by", hold),
        (hold, "meta_of", f"Meta_{company}"),
        (company, "partner_of", part),
        (part, "meta_of", f"PMeta_{company}"),
        (f"DecoyPerson_{company}", "works_at", dco),
    ]
    return edges, person, hq


def main():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    rows = []
    seen = set()
    for r in DATA:
        if r["person"] in seen:
            continue
        seen.add(r["person"])
        rows.append(r)
    rows = rows[:16]
    quiz = rows[3:11]

    for r in ("works_at", "headquartered_in", "owned_by", "partner_of", "meta_of"):
        sealer.atom(r)

    prog_items, scaf_items = [], []
    cases = []
    for i, row in enumerate(quiz):
        edges, person, hq = build_graph(row, rows, rng)
        ctx = render(sealer, edges)
        exp = sealer.atom(hq)
        # Path program (same encoding)
        q_prog = (
            f"PATH_QUERY\n"
            f"START {sealer.atom(person)}\n"
            f"R1 {sealer.atom('works_at')}\n"
            f"R2 {sealer.atom('headquartered_in')}\n"
            f"Execute START -R1-> x -R2-> y. Return y seal only."
        )
        cid = f"REAL_PROG_{i}"
        prog_items.append((cid, f"{q_prog}\n\nCONTEXT:\n{ctx}"))
        cases.append({"id": cid, "cond": "path_program", "expect": exp, "plain_hq": hq})

        # Scaffolded two sealed subgoals in one prompt
        q_scaf = (
            f"Step1: find tail of ({sealer.atom(person)} | {sealer.atom('works_at')} | ?).\n"
            f"Step2: find tail of (?step1 | {sealer.atom('headquartered_in')} | ?).\n"
            f"Return Step2 seal only."
        )
        cids = f"REAL_SCAF_{i}"
        scaf_items.append((cids, f"{q_scaf}\n\nCONTEXT:\n{ctx}"))
        cases.append({"id": cids, "cond": "scaffold", "expect": exp, "plain_hq": hq})

    for name, items, header in [
        ("prog", prog_items, "Sealed path-program query (same encoding)."),
        ("scaf", scaf_items, "Sealed two-step scaffold (same encoding)."),
    ]:
        d = ROOT / "runs" / f"real_{name}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        lines = [
            "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
            "Same encoding. No external knowledge.\n",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
            header + "\n",
        ]
        for cid, body in items:
            lines.append(f"\n##### ID {cid} #####\n{body}\n")
        (d / f"BATCH_{name}.txt").write_text("\n".join(lines))

    (RESULTS / "real_sameenc_fix_harness.json").write_text(
        json.dumps({"cases": cases, "rev": sealer.rev, "prior_fail": "canon stopped at company 0/8"}, indent=2)
    )
    print(json.dumps({"n": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
