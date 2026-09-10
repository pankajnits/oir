from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_custom_three_arm_engine_ceiling(tmp_path):
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/custom_three_arm.py"),
            str(ROOT / "examples/custom_graph.example.json"),
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    out = tmp_path / "custom_graph.example/engine_ceiling.json"
    assert out.is_file(), r.stdout + r.stderr
    d = json.loads(out.read_text())
    assert d["PLAIN_PROG_engine"] == "1/1"
    assert d["SEAL_PROG_engine"] == "1/1"
    bound = (tmp_path / "custom_graph.example/TOY_0_BOUND_NL.txt").read_text()
    nobind = (tmp_path / "custom_graph.example/TOY_0_NOBIND_NL.txt").read_text()
    for prompt in (bound, nobind):
        assert "PATH_QUERY" not in prompt
        assert "Paris" not in prompt
        assert "Alice" not in prompt
        assert "Smith" not in prompt
    row = d["rows"][0]
    assert row["start_in_bound_q"] is True
    assert row["start_in_nobind_q"] is False
