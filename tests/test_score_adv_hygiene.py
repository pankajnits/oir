"""Dual-path scorer must not print 0/n when the arm was never run."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _score_mod():
    spec = importlib.util.spec_from_file_location(
        "score_adv_n32_iso", ROOT / "harness" / "score_adv_n32_iso.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_missing_arm_is_not_run_not_zero():
    cell_score = _score_mod().cell_score
    assert cell_score(0, 32, 32) == "not_run"
    assert cell_score(0, 32, 0) == "0/32"
    assert cell_score(32, 32, 0) == "32/32"
