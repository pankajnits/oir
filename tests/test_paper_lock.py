"""Headline paper numbers must match locked JSON (catches mixed-lock prose)."""
from __future__ import annotations

import json
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
