#!/usr/bin/env python3
"""2Wiki-CF PLAIN_NL n=200: 4 shards of 50 + optional one-quiz files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import SealRouter

SRC = ROOT / "data" / "wiki_cf_n200.json"
RUNS = ROOT / "runs" / "wiki_cf_n200"
RESULTS = ROOT / "results"
SHARD = 50


def pack(items, header):
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No decrypt. No world knowledge.",
        "Format: ANSWER_PLAIN[<id>]: <answer_or_UNKNOWN>",
        "Answer EVERY ID. Gold is the CF tail IN CONTEXT, not Wikipedia.",
        "",
        header,
        "",
    ]
    for cid, body, ctx in items:
        lines.append(f"##### ID {cid} #####\n{body}\n\nCONTEXT:\n{ctx}\n")
    return "\n".join(lines)


def main():
    cases_src = json.loads(SRC.read_text())["cases"]
    cases, shards = [], {}
    RUNS.mkdir(parents=True, exist_ok=True)
    iso = RUNS / "iso_PLAIN"
    iso.mkdir(parents=True, exist_ok=True)
    for c in cases_src:
        cid = f"CF200_PLAINNL_{c['i']}"
        ctx = SealRouter([tuple(e) for e in c["edges"]]).render()
        body = f"QUESTION:\n{c['question']}"
        cases.append(
            {
                "i": c["i"],
                "id": cid,
                "question": c["question"],
                "expect_plain": c["cf_gold"],
                "wiki_answer": c["wiki_answer"],
            }
        )
        one = pack([(cid, body, ctx)], "ARM PLAIN_NL: one quiz. CF tail in CONTEXT, not Wikipedia.")
        (iso / f"{cid}.txt").write_text(one)
        s = c["i"] // SHARD
        shards.setdefault(s, []).append((cid, body, ctx))

    paths = {}
    for s, items in sorted(shards.items()):
        d = RUNS / f"PLAIN_NL_SHARD{s}"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack(items, f"ARM PLAIN_NL shard {s} (n={len(items)}). CF tail in CONTEXT, not Wikipedia."))
        paths[f"shard{s}"] = str(p)

    harness = {
        "n": len(cases),
        "suite": "wiki_cf_n200",
        "shard_size": SHARD,
        "paths": paths,
        "iso_dir": str(iso),
        "cases": cases,
        "falsifier": "PLAIN_NL == original Wikipedia answer → parametric cheat",
        "nonclaim": "Not G-Rev1. English rels readable. Scale of CF PLAIN_NL.",
    }
    out = RESULTS / "wiki_cf_n200_harness.json"
    out.write_text(json.dumps(harness, indent=2, ensure_ascii=False))
    print(json.dumps({"n": len(cases), "shards": list(paths), "iso": len(list(iso.glob('*.txt'))), "out": str(out)}, indent=2))


if __name__ == "__main__":
    main()
