#!/usr/bin/env python3
"""Run OpenAI n=200 inventory. New tags only; never gpt56 / *abl locks.

  python3 harness/run_n200_openai.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
RUN = ROOT / "harness" / "run_openai_iso_harness.py"
TAG = "gpt56n200"
WORKERS = "8"

JOBS = [
    (
        "results/factorial_2x2_iso_n200_harness.json",
        TAG,
        ["--max-completion-tokens", "512", "--workers", WORKERS],
    ),
    (
        "results/header_decoy_ablation_iso_n200_harness.json",
        "gpt56n200abl",
        ["--max-completion-tokens", "4096", "--reasoning-effort", "medium", "--workers", WORKERS],
    ),
    (
        "results/header_decoy_ablation_iso_n200_harness.json",
        "gpt56n200h512",
        ["OPQ_H5_CYC", "--max-completion-tokens", "512", "--workers", WORKERS],
    ),
    (
        "results/entity_rel_2x2_iso_n200_harness.json",
        TAG,
        ["--max-completion-tokens", "512", "--workers", WORKERS],
    ),
    (
        "results/factorial_2x2_iso_shuffle_n200_harness.json",
        TAG,
        ["--max-completion-tokens", "512", "--workers", WORKERS],
    ),
    (
        "results/ceiling_three_arm_n200_iso_harness.json",
        TAG,
        ["--max-completion-tokens", "512", "--workers", WORKERS],
    ),
    (
        "results/metaqa_2x2_people_n200_iso_harness.json",
        TAG,
        ["--max-completion-tokens", "512", "--workers", WORKERS],
    ),
    (
        "results/metaqa_2x2_people_n200_qhash_iso_harness.json",
        TAG,
        ["--max-completion-tokens", "512", "--workers", WORKERS],
    ),
    (
        "results/dualpath_wikimovies_iso_n200_harness.json",
        TAG,
        ["--max-completion-tokens", "512", "--workers", WORKERS],
    ),
]


def main() -> None:
    for harness, tag, extra in JOBS:
        cmd = [PY, str(RUN), str(ROOT / harness), tag, *extra]
        print("+", " ".join(cmd), flush=True)
        subprocess.check_call(cmd, cwd=ROOT)
    scores = [
        [PY, str(ROOT / "harness/score_factorial_2x2.py"), TAG, "factorial_2x2_iso_n200_harness"],
        [PY, str(ROOT / "harness/header_decoy_ablation_iso.py"), "score", "gpt56n200abl",
         str(ROOT / "results/header_decoy_ablation_iso_n200_harness.json")],
        [PY, str(ROOT / "harness/header_decoy_ablation_iso.py"), "score", "gpt56n200h512",
         str(ROOT / "results/header_decoy_ablation_iso_n200_harness.json")],
        [PY, str(ROOT / "harness/score_factorial_2x2.py"), TAG, "entity_rel_2x2_iso_n200_harness"],
        [PY, str(ROOT / "harness/score_factorial_2x2.py"), TAG, "factorial_2x2_iso_shuffle_n200_harness"],
        [PY, str(ROOT / "harness/score_ceiling_n32_iso.py"), TAG, "ceiling_three_arm_n200_iso_harness"],
        [PY, str(ROOT / "harness/score_factorial_2x2.py"), TAG, "metaqa_2x2_people_n200_iso_harness"],
        [PY, str(ROOT / "harness/score_factorial_2x2.py"), TAG, "metaqa_2x2_people_n200_qhash_iso_harness"],
        [PY, str(ROOT / "harness/score_factorial_2x2.py"), TAG, "dualpath_wikimovies_iso_n200_harness"],
    ]
    for cmd in scores:
        print("+", " ".join(cmd), flush=True)
        subprocess.check_call(cmd, cwd=ROOT)
    print("n=200 OpenAI scored", flush=True)


if __name__ == "__main__":
    main()
