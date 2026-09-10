#!/usr/bin/env python3
"""Print / optionally draft Task prompts for balanced trap MUTs (model selection).

Usage:
  python3 harness/prep_balanced_mut.py gpt56
  python3 harness/prep_balanced_mut.py claude_sonnet
  python3 harness/prep_balanced_mut.py gpt56 --missing-only

After MUT replies exist under results/adv_induction_replies_<tag>/<ARM>/item_i.txt:
  python3 harness/score_adv_model.py <tag>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs

HARNESS = ROOT / "results" / "adv_induction_harness.json"
ARMS = ["SAME_BALANCED", "CROSS_BALANCED"]


def reply_path(tag: str, arm: str, i: int) -> Path:
    return ROOT / "results" / f"adv_induction_replies_{tag}" / arm / f"item_{i}.txt"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", help="gpt56 | claude_sonnet | ...")
    ap.add_argument("--missing-only", action="store_true")
    args = ap.parse_args()
    h = json.loads(HARNESS.read_text())
    for arm in ARMS:
        meta = h["arms"][arm]
        for i, (cid, ptxt) in enumerate(zip(meta["ids"], meta["item_paths"])):
            out = reply_path(args.tag, arm, i)
            if args.missing_only and out.exists() and "UNKNOWN" not in out.read_text().upper():
                continue
            print("=" * 72)
            print(f"TAG={args.tag} ARM={arm} item={i} id={cid}")
            print(f"WRITE → {out}")
            print(f"MODEL: gpt-5.6-sol-medium  OR  claude-sonnet-5-thinking-high")
            print(
                "PROMPT:\n"
                f"STRICT ISOLATION MUT. Read ONLY this one file with the Read tool:\n{repo_abs(ptxt)}\n"
                "Forbidden: any other path, Grep, Glob, Shell, workspace search, decrypt, world knowledge.\n"
                f"Return ONLY one line exactly: ANSWER_SEALED[{cid}]: <seal_or_UNKNOWN>\n"
                "No commentary."
            )


if __name__ == "__main__":
    main()
