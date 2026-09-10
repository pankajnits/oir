"""Headline paper numbers must match locked JSON (catches mixed-lock prose)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

NONCITY = {
    "Broadway",
    "NRK_Marienlyst",
    "Fox_Plaza",
    "CNN_Center",
    "Lod_Railway_Station",
    "New_Jersey",
}


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


def test_wiki_h5_openai_headline():
    s = _load("factorial_2x2_iso_gpt56.json")["summary"]
    assert s["ENG_UNIQUE"]["score"] == "31/32"
    assert s["ENG_AMBIG"]["score"] == "31/32"
    assert s["OPAQUE_UNIQUE"]["score"] == "32/32"
    assert s["OPAQUE_AMBIG"]["score"] == "6/32"
    assert s["OPAQUE_AMBIG"]["decoy"] == 2
    assert s["OPAQUE_AMBIG"]["unknown"] == 24
    assert s["OPAQUE_AMBIG_PLAN"]["score"] == "32/32"


def test_dualpath_isolation_composer_abstains_on_novel_asymmetric():
    """Body isolation lock: composer25, not composer25ff."""
    s = _load("adv_induction_n32_iso_composer25.json")["summary"]
    assert s["CROSS_TRAP"]["score"] == "0/32"
    assert s["CROSS_TRAP"]["trap_rate"] == "0/32"
    assert s["CROSS_TRAP"]["unknown"] == 32


def test_dualpath_freeform_composer_takes_novel_asymmetric_decoy():
    s = _load("adv_induction_n32_iso_composer25ff.json")["summary"]
    assert s["CROSS_TRAP"]["score"] == "0/32"
    assert s["CROSS_TRAP"]["trap_rate"] == "32/32"


def test_city_subset_non_twopath_errors_are_only_noncity():
    for fname in (
        "factorial_2x2_iso_gpt56.json",
        "factorial_2x2_iso_composer25.json",
        "factorial_2x2_iso_grok45.json",
    ):
        rows = _load(fname)["rows"]
        for r in rows:
            if r["arm"] in {"OPAQUE_AMBIG", "ENG_AMBIG"}:
                continue
            if not r["ok"]:
                assert r["gold"] in NONCITY, (fname, r["arm"], r["gold"], r.get("pred"))


def test_sha256sums_lists_only_tracked_json():
    """Fresh clones must be able to run ``shasum -c results/SHA256SUMS`` from the repo root."""
    listed = []
    for line in (RESULTS / "SHA256SUMS").read_text().splitlines():
        digest, rel = line.split(None, 1)
        listed.append(rel)
        path = ROOT / rel
        assert path.is_file(), rel
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, rel
        r = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", "--", rel],
        )
        assert r.returncode == 1, f"gitignored but listed: {rel}"
    assert "results/longctx_1m_harness.json" not in listed
    assert "results/longctx_1m_results.json" not in listed
    tracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "results/"],
    )
    tracked_json = {
        p for p in tracked.decode().split("\0") if p.endswith(".json")
    }
    assert set(listed) == tracked_json
