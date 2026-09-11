#!/usr/bin/env python3
"""Run composer-2.5 and grok-4.5 on public suites OpenAI already finished.

Skips OpenAI. Skips OO_UNIQUE/OO_AMBIG (already scored for both families).
Does not run WikiMovies n=100.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_venv_py = ROOT / ".venv" / "bin" / "python"
PY = _venv_py if _venv_py.exists() else Path(sys.executable)
RUNNER = ROOT / "harness" / "run_iso_agent_harness.py"
SCORE = ROOT / "harness" / "score_factorial_2x2.py"

JOBS = [
    ("results/factorial_2x2_iso_harness.json", None, "factorial_2x2_iso_harness"),
    (
        "results/entity_rel_2x2_iso_harness.json",
        ["OE_UNIQUE", "OE_AMBIG", "OO_AMBIG_PLAN"],
        "entity_rel_2x2_iso_harness",
    ),
    ("results/metaqa_2x2_people_iso_harness.json", None, "metaqa_2x2_people_iso_harness"),
    ("results/dualpath_wikimovies_iso_harness.json", None, "dualpath_wikimovies_iso_harness"),
    ("results/metaqa_official_iso_harness.json", None, "metaqa_official_iso_harness"),
    ("results/perm_2x2_iso_harness.json", None, "perm_2x2_iso_harness"),
    ("results/ambig_curve_iso_harness.json", None, "ambig_curve_iso_harness"),
]
MODELS = [("composer25", "composer-2.5"), ("grok45", "grok-4.5")]


def main() -> None:
    if not os.environ.get("AGENT_API_KEY") and not os.environ.get("CURSOR_API_KEY"):
        raise SystemExit("Set AGENT_API_KEY or CURSOR_API_KEY")
    conc = os.environ.get("OIR_CONCURRENCY", "4")
    for tag, model in MODELS:
        for harness, arms, stem in JOBS:
            cmd = [
                str(PY),
                str(RUNNER),
                str(ROOT / harness),
                tag,
                model,
                "--concurrency",
                conc,
            ]
            if arms:
                cmd.extend(arms)
            print("==>", " ".join(cmd[-8:]), flush=True)
            try:
                subprocess.check_call(cmd, cwd=str(ROOT))
                subprocess.check_call(
                    [sys.executable, str(SCORE), tag, stem], cwd=str(ROOT)
                )
            except subprocess.CalledProcessError as e:
                print(f"FAILED {tag} {stem}: {e}", flush=True)
                continue


if __name__ == "__main__":
    main()
