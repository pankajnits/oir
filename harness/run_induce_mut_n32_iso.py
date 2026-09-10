#!/usr/bin/env python3
"""
Sealed-demo MUT helper for n=32 iso dual-path probes.

For each prompt.txt: apply sealed demonstration binding
(majority DEMO 2-hop relation seals → follow on QUIZ; else UNKNOWN).
Does NOT read harness gold. Used when Grok 4.5 runs the
MUT protocol in-session; composer-2.5 should answer without this script when
possible, or the same procedure if acting as a careful agent.

Lab arm ids (filenames) → paper names:
  SAME_TRAP      → matched-relation, asymmetric noise
  CROSS_TRAP     → novel-relation, asymmetric noise
  SAME_BALANCED  → matched-relation, balanced noise
  CROSS_BALANCED → novel-relation, balanced noise
  PATH_TRAP      → explicit join plan (use engine replies)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs
from induce_follow_n32_iso import answer_prompt  # noqa: E402

RESULTS = ROOT / "results"
HARNESS = RESULTS / "adv_induction_n32_iso_harness.json"
ARMS = ["SAME_TRAP", "CROSS_TRAP", "SAME_BALANCED", "CROSS_BALANCED"]


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "grok45"
    arms = [a for a in sys.argv[2:] if a in ARMS] or ARMS
    h = json.loads(HARNESS.read_text())
    root = RESULTS / f"adv_n32_iso_replies_{tag}"
    for arm in arms:
        meta = h["arms"][arm]
        out_dir = root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(meta["item_paths"]):
            text = repo_abs(p).read_text()
            cid, pred = answer_prompt(text)
            assert cid == meta["ids"][i]
            (out_dir / f"item_{i}.txt").write_text(
                f"ANSWER_SEALED[{cid}]: {pred}\n"
                f"# induce_mut tag={tag} method=sealed_demo_binding prompt_only\n"
            )
        print(arm, len(meta["ids"]))
    print("done", tag, arms)


if __name__ == "__main__":
    main()
