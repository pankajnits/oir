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


def _cell_n(cell: dict) -> int:
    return sum(int(cell.get(k, 0)) for k in (
        "gold", "decoy", "unknown", "other", "no_output", "error", "missing",
    ))


def test_wiki_h5_openai_headline():
    s = _load("factorial_2x2_iso_gpt56.json")["summary"]
    assert s["ENG_UNIQUE"]["score"] == "31/32"
    assert s["ENG_AMBIG"]["score"] == "31/32"
    assert s["OPAQUE_UNIQUE"]["score"] == "32/32"
    assert s["OPAQUE_AMBIG"]["score"] == "6/32"
    assert s["OPAQUE_AMBIG"]["decoy"] == 2
    assert s["OPAQUE_AMBIG"]["unknown"] == 24
    assert s["OPAQUE_AMBIG_PLAN"]["score"] == "32/32"


def test_wiki_h5_composer_grok_named_arm_not_overwritten():
    """Locked Composer/Grok Wiki-H5 two-path cells must stay the August files."""
    assert _load("factorial_2x2_iso_composer25.json")["summary"]["OPAQUE_AMBIG"]["score"] == "10/32"
    assert _load("factorial_2x2_iso_grok45.json")["summary"]["OPAQUE_AMBIG"]["score"] == "1/32"


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


def test_header_decoy_ablation_openai_gold_counts():
    blob = _load("header_decoy_ablation_iso_gpt56abl.json")
    s = blob["cells"]
    assert all(_cell_n(c) == 32 for c in s.values())
    assert s["OPQ_H5_CYC"]["gold"] == 20
    assert s["OPQ_H5_CRV"]["gold"] == 10
    assert s["OPQ_K2_CYC"]["gold"] == 30
    assert s["OPQ_K2_CRV"]["gold"] == 26
    assert s["OPQ_NONE_CYC"]["gold"] == 25
    assert s["OPQ_NONE_CRV"]["gold"] == 27
    assert s["ENG_NONE_CYC"]["gold"] == 29
    sep_blob = _load("factorial_2x2_iso_gpt56sep.json")
    sep = sep_blob["summary"]["OPAQUE_AMBIG"]
    assert sep["score"] == "5/32"
    assert sep["missing"] == 0
    assert sum(1 for r in sep_blob["rows"] if r["arm"] == "OPAQUE_AMBIG" and r["pred"] == "NO_OUTPUT") == 1
    assert "note" in blob and "4096" in blob["note"]
    h5_512 = _load("header_decoy_ablation_iso_gpt56abl512.json")["cells"]["OPQ_H5_CYC"]
    assert h5_512["gold"] == 20
    assert _load("header_decoy_ablation_iso_gpt56abl512.json")["cells"]["OPQ_H5_CRV"]["missing"] == 32


def test_header_decoy_ablation_composer_grok_gold_counts():
    c = _load("header_decoy_ablation_iso_composer25abl.json")["cells"]
    g = _load("header_decoy_ablation_iso_grok45abl.json")["cells"]
    assert all(_cell_n(cell) == 32 for cell in (*c.values(), *g.values()))
    assert c["OPQ_H5_CYC"]["gold"] == 6
    assert c["OPQ_H5_CRV"]["gold"] == 1
    assert c["OPQ_K2_CYC"]["gold"] == 19
    assert c["OPQ_K2_CRV"]["gold"] == 13
    assert c["OPQ_NONE_CYC"]["gold"] == 21
    assert c["OPQ_NONE_CRV"]["gold"] == 17
    assert c["ENG_NONE_CYC"]["gold"] == 25
    assert g["OPQ_H5_CYC"].get("gold", 0) == 0
    assert g["OPQ_H5_CRV"].get("gold", 0) == 0
    assert g["OPQ_K2_CYC"].get("gold", 0) == 0
    assert g["OPQ_K2_CRV"].get("gold", 0) == 0
    assert g["OPQ_NONE_CYC"]["gold"] == 6
    assert g["OPQ_NONE_CRV"]["gold"] == 1
    assert g["ENG_NONE_CYC"]["gold"] == 24


def test_sha256sums_lists_tracked_json_and_replies():
    """Fresh clones must be able to run ``shasum -c results/SHA256SUMS`` from the repo root."""
    listed = []
    for line in (RESULTS / "SHA256SUMS").read_text().splitlines():
        digest, rel = line.split(None, 1)
        listed.append(rel)
        path = ROOT / rel
        assert path.is_file(), rel
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, rel
    assert "results/longctx_1m_harness.json" not in listed
    assert "results/longctx_1m_results.json" not in listed
    tracked = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "results/"],
    )
    tracked_evidence = {
        p
        for p in tracked.decode().split("\0")
        if p.endswith((".json", ".txt"))
    }
    assert set(listed) == tracked_evidence
    # git ls-files already omits gitignored paths; do not spawn check-ignore per file.
