#!/usr/bin/env python3
"""2Wiki-CF PLAIN_NL n=32 from frozen wiki_cf_n200 (parametric kill at scale)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import SealRouter

SRC = ROOT / "data" / "wiki_cf_n200.json"
RUNS = ROOT / "runs" / "wiki_cf_n32"
RESULTS = ROOT / "results"
N = 32


def pack(items):
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No decrypt. No world knowledge.",
        "Format: ANSWER_PLAIN[<id>]: <answer_or_UNKNOWN>",
        "Answer EVERY ID. Gold is the CF tail IN CONTEXT, not Wikipedia.",
        "",
        "ARM PLAIN_NL n=32: English question + plaintext KG with a counterfactual hop-2 tail.",
        "",
    ]
    for cid, body, ctx in items:
        lines.append(f"##### ID {cid} #####\n{body}\n\nCONTEXT:\n{ctx}\n")
    return "\n".join(lines)


def main():
    cases_all = json.loads(SRC.read_text())["cases"][:N]
    items, cases = [], []
    for c in cases_all:
        cid = f"CF32_PLAINNL_{c['i']}"
        ctx = SealRouter([tuple(e) for e in c["edges"]]).render()
        items.append((cid, f"QUESTION:\n{c['question']}", ctx))
        cases.append(
            {
                "i": c["i"],
                "id": cid,
                "question": c["question"],
                "expect_plain": c["cf_gold"],
                "wiki_answer": c["wiki_answer"],
            }
        )
    RUNS.mkdir(parents=True, exist_ok=True)
    p = RUNS / "PLAIN_NL_ONLY" / "BATCH.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(pack(items))
    harness = {
        "n": N,
        "suite": "wiki_cf_n32",
        "path": str(p),
        "cases": cases,
        "source": "data/wiki_cf_n200.json[:32]",
        "falsifier": "PLAIN_NL == original Wikipedia answer → parametric cheat",
        "nonclaim": "Not G-Rev1. Scale check of CF PLAIN_NL. English rels still readable.",
    }
    out = RESULTS / "wiki_cf_n32_harness.json"
    out.write_text(json.dumps(harness, indent=2, ensure_ascii=False))
    print(json.dumps({"n": N, "out": str(out), "batch": str(p)}, indent=2))


if __name__ == "__main__":
    main()
