"""Clone-and-run middleware example must stay green without a network."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_middleware_hr_example():
    r = subprocess.run(
        [sys.executable, str(ROOT / "examples/middleware_hr.py")],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert "decoded: San Francisco" in r.stdout
    assert "engine_ok: True" in r.stdout
    assert "nobind_misses_start: True" in r.stdout
    assert "join_hmac_hides_gold: True" in r.stdout
    assert r.stdout.strip().endswith("ok")
