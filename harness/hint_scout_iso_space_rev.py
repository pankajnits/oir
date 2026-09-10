#!/usr/bin/env python3
"""Control: same iso/encoding-space push, but gold 2-hop listed SECOND.

If the 20/20 scout was first-path bias, reversed CONTEXT should flip to decoy.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs  # type: ignore
from hint_scout_iso_space import (  # type: ignore
    ISO_HASHED,
    ISO_UNHASHED,
    complete,
    inject,
    kind,
    load_env,
    parse,
)

OUT = ROOT / "results" / "hint_scout_iso_space_rev.json"
REPLY = ROOT / "results" / "hint_scout_iso_space_rev_replies"


def reverse_two_hops(prompt: str) -> str:
    pre, ctx = prompt.split("CONTEXT:\n", 1)
    lines = [ln for ln in ctx.splitlines() if ln.strip()]
    if len(lines) == 3:
        # start-mid; mid-gold; mid-decoy  (WikiMovies)
        lines = [lines[0], lines[2], lines[1]]
    elif len(lines) == 4:
        # hop1a, hop1b (gold), hop2a, hop2b (decoy)
        lines = [lines[2], lines[3], lines[0], lines[1]]
    else:
        raise SystemExit(f"unexpected context lines {len(lines)}")
    return pre + "CONTEXT:\n" + "\n".join(lines) + "\n"


def main() -> None:
    load_env()
    model = os.environ.get("OIR_MODEL", "gpt-5.6-sol")
    client = OpenAI()
    REPLY.mkdir(parents=True, exist_ok=True)
    specs = [
        (
            "wiki_hashed_rev",
            "results/metaqa_2x2_people_n100_qhash_iso_harness.json",
            "OPAQUE_AMBIG",
            [0, 1, 2, 3],
            False,
            ISO_HASHED,
        ),
        (
            "oo_rev",
            "results/entity_rel_2x2_iso_harness.json",
            "OO_AMBIG",
            [0, 1, 2, 3],
            True,
            ISO_UNHASHED,
        ),
        (
            "wd_rev",
            "results/factorial_2x2_iso_harness.json",
            "OPAQUE_AMBIG",
            [0, 1, 3, 4],
            False,
            ISO_UNHASHED,
        ),
    ]
    rows = []
    for suite, harness, arm, idxs, sealed, hint in specs:
        h = json.loads((ROOT / harness).read_text())
        cases = {c["i"]: c for c in h["cases"]}
        paths = h["arms"][arm]["item_paths"]
        ids = h["arms"][arm]["ids"]
        for i in idxs:
            prompt = reverse_two_hops(inject(repo_abs(paths[i]).read_text(), hint))
            case = cases[i]
            if suite == "oo_rev":
                gold, decoy = case["golds"][arm], case["decoys"][arm]
            else:
                gold, decoy = case["gold"], case["decoy_hq"]
            cid = ids[i]
            t0 = time.time()
            raw = complete(client, model, prompt)
            pred = parse(cid, raw, sealed=sealed)
            k = kind(pred, gold, decoy)
            rec = {
                "suite": suite,
                "i": i,
                "id": cid,
                "pred": pred,
                "gold": gold,
                "decoy": decoy,
                "kind": k,
                "sec": round(time.time() - t0, 1),
            }
            rows.append(rec)
            (REPLY / f"{suite}_{i}.txt").write_text(f"{pred}\n# raw\n{raw[:4000]}\n")
            print(f"{suite} {i} {rec['sec']}s -> {k} {pred}", flush=True)
    summary: dict[str, dict[str, int]] = {}
    for r in rows:
        summary.setdefault(
            r["suite"], {"gold": 0, "decoy": 0, "unknown": 0, "other": 0, "n": 0}
        )
        summary[r["suite"]][r["kind"]] += 1
        summary[r["suite"]]["n"] += 1
    OUT.write_text(
        json.dumps({"note": "gold 2-hop listed second", "summary": summary, "rows": rows}, indent=2)
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
