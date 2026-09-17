"""Headline paper numbers must match locked JSON (catches mixed-lock prose)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

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
    assert sep.get("no_output") == 1
    assert sum(1 for r in sep_blob["rows"] if r["arm"] == "OPAQUE_AMBIG" and r["pred"] == "NO_OUTPUT") == 1
    for arm in ("ENG_UNIQUE", "ENG_AMBIG", "OPAQUE_UNIQUE", "OPAQUE_AMBIG_PLAN"):
        assert sep_blob["summary"][arm]["score"] == "n.r."
        assert sep_blob["summary"][arm]["missing"] == 32
    assert "note" in blob and "4096" in blob["note"]
    h5_512 = _load("header_decoy_ablation_iso_gpt56abl512.json")["cells"]["OPQ_H5_CYC"]
    assert h5_512["gold"] == 20
    assert _load("header_decoy_ablation_iso_gpt56abl512.json")["cells"]["OPQ_H5_CRV"]["missing"] == 32


def test_header_decoy_ablation_composer_grok_gold_counts():
    c = _load("header_decoy_ablation_iso_composer25abl.json")["cells"]
    g = _load("header_decoy_ablation_iso_grok45abl.json")["cells"]
    assert all(_cell_n(cell) == 32 for cell in (*c.values(), *g.values()))
    assert c["OPQ_H5_CYC"]["gold"] == 6
    assert c["OPQ_H5_CRV"]["gold"] == 2
    assert c["OPQ_K2_CYC"]["gold"] == 20
    assert c["OPQ_K2_CRV"]["gold"] == 13
    assert c["OPQ_NONE_CYC"]["gold"] == 21
    assert c["OPQ_NONE_CRV"]["gold"] == 18
    assert c["ENG_NONE_CYC"]["gold"] == 26
    assert g["OPQ_H5_CYC"].get("gold", 0) == 0
    assert g["OPQ_H5_CRV"].get("gold", 0) == 0
    assert g["OPQ_K2_CYC"].get("gold", 0) == 0
    assert g["OPQ_K2_CRV"].get("gold", 0) == 0
    assert g["OPQ_NONE_CYC"]["gold"] == 6
    assert g["OPQ_NONE_CRV"]["gold"] == 1
    assert g["ENG_NONE_CYC"]["gold"] == 24


def test_locked_full_ablation_has_no_incompletes():
    """Complete-case McNemar equals ITT on the three 7-arm locks (no empty/error)."""
    for name in (
        "header_decoy_ablation_iso_gpt56abl.json",
        "header_decoy_ablation_iso_composer25abl.json",
        "header_decoy_ablation_iso_grok45abl.json",
    ):
        for arm, cell in _load(name)["cells"].items():
            assert cell.get("no_output", 0) == 0, (name, arm)
            assert cell.get("error", 0) == 0, (name, arm)
            assert cell.get("missing", 0) == 0, (name, arm)


def test_composer25tx_does_not_replace_august_lock():
    """Supplemental transcript rerun; August composer25 JSON stays the paper lock."""
    lock = _load("entity_rel_2x2_iso_composer25.json")["summary"]
    assert lock["OO_UNIQUE"]["score"] == "32/32"
    assert lock["OO_AMBIG"]["score"] == "0/32"
    assert lock["OO_AMBIG"]["unknown"] == 32
    assert lock["OO_AMBIG"]["decoy"] == 0
    tx_path = RESULTS / "entity_rel_2x2_iso_composer25tx.json"
    if not tx_path.is_file():
        pytest.skip("composer25tx supplemental JSON is not in this tree")
    tx = json.loads(tx_path.read_text())
    assert "does not replace" in tx.get("note", "").lower()
    assert tx["summary"]["OO_UNIQUE"]["score"] == "32/32"
    assert tx["summary"]["OO_AMBIG"]["score"] == "0/32"
    ceil = json.loads((RESULTS / "ceiling_three_arm_n32_iso_composer25tx.json").read_text())
    assert ceil["summary"]["SEAL_NL"]["score"] == "0/32"
    assert ceil["summary"]["PLAIN_PROG"]["score"] == "n.r."
    assert ceil["summary"]["SEAL_PROG"]["score"] == "n.r."
    rd = ceil.get("reply_dir", "")
    assert not rd.startswith("/"), rd
    assert "pankaj" not in rd.lower()
    assert rd.endswith("ceiling_three_arm_n32_iso_harness_replies_composer25tx")
    assert _load("ceiling_three_arm_n32_iso_composer25.json")["summary"]["SEAL_NL"]["score"] == "0/32"


def test_city_subset_english_twopath():
    """City-valued English two-path: Composer format, Grok abstention, OpenAI ceiling."""
    def _city_ok(fname: str) -> tuple[int, int]:
        rows = [r for r in _load(fname)["rows"] if r["arm"] == "ENG_AMBIG"]
        city = [r for r in rows if r["gold"] not in NONCITY]
        return sum(1 for r in city if r["ok"]), len(city)

    assert _city_ok("factorial_2x2_iso_gpt56.json") == (26, 26)
    assert _city_ok("factorial_2x2_iso_composer25.json") == (26, 26)
    assert _city_ok("factorial_2x2_iso_grok45.json") == (4, 26)


def test_k3_openai_wiki_h5_does_not_replace_august_lock():
    """August gpt56 stays the lock; k=3 draws are extra snapshots of the alias."""
    lock = _load("factorial_2x2_iso_gpt56.json")["summary"]
    assert lock["OPAQUE_AMBIG"]["score"] == "6/32"
    assert lock["OPAQUE_UNIQUE"]["score"] == "32/32"
    r2 = _load("factorial_2x2_iso_gpt56k3r2.json")
    r3 = _load("factorial_2x2_iso_gpt56k3r3.json")
    assert "does not replace" in r2.get("note", "").lower()
    assert "does not replace" in r3.get("note", "").lower()
    assert r2["summary"]["OPAQUE_AMBIG"]["score"] == "3/32"
    assert r3["summary"]["OPAQUE_AMBIG"]["score"] == "3/32"
    assert r2["summary"]["OPAQUE_AMBIG_PLAN"]["score"] == "32/32"
    assert r3["summary"]["OPAQUE_AMBIG_PLAN"]["score"] == "32/32"
    assert r2["summary"]["ENG_UNIQUE"]["score"] == "32/32"
    assert r3["summary"]["ENG_UNIQUE"]["score"] == "32/32"
    sidecar = json.loads(
        (RESULTS / "factorial_2x2_iso_harness_replies_gpt56k3r2" / "OPAQUE_AMBIG" / "item_0.json").read_text()
    )
    assert sidecar.get("returned_model") == "gpt-5.6-sol"


def test_k3_header_h5_cyclic_stays_high():
    assert _load("header_decoy_ablation_iso_gpt56abl512.json")["cells"]["OPQ_H5_CYC"]["gold"] == 20
    r2 = _load("header_decoy_ablation_iso_gpt56h5k3r2.json")
    r3 = _load("header_decoy_ablation_iso_gpt56h5k3r3.json")
    assert "does not replace" in r2.get("note", "").lower()
    assert "does not replace" in r3.get("note", "").lower()
    assert r2["cells"]["OPQ_H5_CYC"]["gold"] == 21
    assert r3["cells"]["OPQ_H5_CYC"]["gold"] == 22
    assert r2["cells"]["OPQ_H5_CRV"]["missing"] == 32
    assert r3["cells"]["OPQ_H5_CRV"]["missing"] == 32


def test_k3_composer_grok_opaque_ambig_does_not_replace_august():
    assert _load("factorial_2x2_iso_composer25.json")["summary"]["OPAQUE_AMBIG"]["score"] == "10/32"
    assert _load("factorial_2x2_iso_grok45.json")["summary"]["OPAQUE_AMBIG"]["score"] == "1/32"
    c2 = _load("factorial_2x2_iso_composer25k3r2.json")
    c3 = _load("factorial_2x2_iso_composer25k3r3.json")
    g2 = _load("factorial_2x2_iso_grok45k3r2.json")
    g3 = _load("factorial_2x2_iso_grok45k3r3.json")
    for blob in (c2, c3, g2, g3):
        assert "does not replace" in blob.get("note", "").lower()
        assert blob["summary"]["ENG_UNIQUE"]["score"] == "n.r."
    assert c2["summary"]["OPAQUE_AMBIG"]["score"] == "7/32"
    assert c3["summary"]["OPAQUE_AMBIG"]["score"] == "6/32"
    assert g2["summary"]["OPAQUE_AMBIG"]["score"] == "0/32"
    assert g3["summary"]["OPAQUE_AMBIG"]["score"] == "0/32"
    for tag, model in (("composer25k3r2", "composer-2.5"), ("grok45k3r2", "grok-4.5")):
        sidecar = json.loads(
            (RESULTS / f"factorial_2x2_iso_harness_replies_{tag}" / "OPAQUE_AMBIG" / "item_0.json").read_text()
        )
        assert sidecar.get("preamble") == "cursor"
        assert sidecar.get("model") == model


def test_grok45pn_named_arm_english_matches_lock_and_does_not_replace():
    """Prompt-verbatim Grok named-arm English stays 4/32; August grok45 is untouched."""
    pn = _load("factorial_2x2_iso_grok45pn.json")
    assert "does not replace" in pn.get("note", "").lower()
    assert pn["summary"]["ENG_AMBIG"]["score"] == "4/32"
    assert pn["summary"]["ENG_AMBIG"]["unknown"] == 28
    for arm in ("ENG_UNIQUE", "OPAQUE_UNIQUE", "OPAQUE_AMBIG", "OPAQUE_AMBIG_PLAN"):
        assert pn["summary"][arm]["score"] == "n.r."
    lock = _load("factorial_2x2_iso_grok45.json")["summary"]
    assert lock["ENG_AMBIG"]["score"] == "4/32"
    assert lock["OPAQUE_AMBIG"]["score"] == "1/32"
    reply_dir = RESULTS / "factorial_2x2_iso_harness_replies_grok45pn" / "ENG_AMBIG"
    txts = sorted(reply_dir.glob("item_*.txt"))
    sidecars = sorted(reply_dir.glob("item_*.json"))
    assert len(txts) == 32
    assert len(sidecars) == 32
    for path in sidecars:
        blob = json.loads(path.read_text())
        assert blob.get("preamble") == "none"
        assert blob.get("model") == "grok-4.5"


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
    for rel in (
        "results/factorial_2x2_iso_n200_gpt56n200k3r2.json",
        "results/factorial_2x2_iso_n200_gpt56n200k3r3.json",
        "results/header_decoy_ablation_iso_n200_gpt56n200h512k3r2.json",
        "results/header_decoy_ablation_iso_n200_gpt56n200h512k3r3.json",
        "results/factorial_2x2_iso_n200_gpt56n200.json",
        "results/header_decoy_ablation_iso_n200_gpt56n200h512.json",
        "results/unique_no_arm_iso_gpt56uninone.json",
        "results/unique_no_arm_iso_n200_gpt56n200uninone.json",
    ):
        assert rel in listed, rel
    git_dir = ROOT / ".git"
    if not git_dir.exists():
        pytest.skip("no .git (zip/export); SHA256SUMS hashes already checked")
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


def test_arxiv_tex_does_not_collapse_h8_or_named_arm():
    tex_path = ROOT / "paper/arxiv_upload/main.tex"
    if not tex_path.is_file():
        pytest.skip("named TeX omitted from supplementary zip")
    tex = tex_path.read_text()
    assert "varies only relation" not in tex
    assert "recover joins rather than guesses" not in tex
    assert r"McNemar $25$ vs.\ $2$" in tex
    start = tex.find("H8. Prompt surface")
    assert start != -1
    h8 = tex[start : start + 450]
    assert "95" not in h8
    assert r"$4$ vs.\ $111$" in h8
    assert "Without Relation Names" in tex
    assert "Without Lexical Cues" not in tex
    assert r"Two-path K2 and no-ARM were not run at 512" in tex
    assert r"hashed-id no-ARM $200/200$ at 512 tokens" in tex
    assert "municipality of the Czech Republic" in tex
    assert "city of Japan" not in tex
    assert "OE\\_UNIQUE" in tex
    assert "OO\\_AMBIG" in tex
    assert r"\texttt{F200\_}" in tex
    assert "vendor alias" in tex
    assert "Hypothesis H5 in this table" not in tex
    assert "row OA is the opacity" in tex
    assert "row H5 is the opacity" not in tex
    assert "Call it English" not in tex
    assert "arm-neutral English" not in tex
    assert "2 same-type 2-hop(s) from start" in tex
    assert "Sign-flip of the H5 interaction" not in tex
    assert r"$n{=}6$ batch" in tex
    abs_ = tex.split(r"\begin{abstract}", 1)[1].split(r"\end{abstract}", 1)[0]
    assert "A \\textbf{lock} is a scored JSON" not in abs_
    assert r"$3{=}3$" not in tex
    assert r"Hashed-id $n{=}32$ 11~Sep 512 & \texttt{gpt56sep}" not in tex
    assert r"\texttt{gpt56abl512}" in tex
    assert "index tail" in tex
    assert r"\texttt{LEGEND}" in tex
