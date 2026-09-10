"""Clone-and-run paper spine demo — no network, no runs/ rewrite."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_paper_spine_example():
    r = subprocess.run(
        [sys.executable, str(ROOT / "examples/paper_spine.py")],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert r.stdout.strip().endswith("ok")
    assert "FAIL" not in r.stdout
    for needle in (
        "H1",
        "H5",
        "H2",
        "H3",
        "H4",
        "H6",
        "H7",
        "32/32",
        "6/32",
        "5/32",
        json.loads((ROOT / "results/metaqa_2x2_people_n100_qhash_iso_gpt56.json").read_text())["summary"]["OPAQUE_AMBIG"]["score"],
        "not a selection result",
    ):
        assert needle in r.stdout, needle
    # Must not pretend this is a model re-run.
    assert "not a re-run of n=32" in r.stdout
    assert "composer 10/32" in r.stdout
    assert "Grok 1/32" in r.stdout or "Grok 4/32" in r.stdout
