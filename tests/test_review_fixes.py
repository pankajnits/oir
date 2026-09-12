"""Regression tests for the pre-publication review fixes (no network)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from oir import EntitySeal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "harness" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rp = _load("reply_parse")


def test_empty_completion_is_no_output_not_unknown():
    pred, text = rp.parse("X", "", sealed=False)
    assert pred == rp.NO_OUTPUT
    assert rp.classify(text) == "no_output"
    assert not rp.is_final(text)


def test_non_empty_replies_parse_as_before():
    pred, text = rp.parse("X", "reasoning\nANSWER_PLAIN[X]: UNKNOWN", sealed=False)
    assert (pred, rp.classify(text), rp.is_final(text)) == ("UNKNOWN", "explicit_unknown", True)
    pred, text = rp.parse("X", "ANSWER_PLAIN[X]: Burbank", sealed=False)
    assert (pred, rp.classify(text)) == ("Burbank", "explicit_answer")


def test_markdown_wrappers_do_not_prevent_gold_match():
    assert rp.clean_pred("Burbank**") == "Burbank"
    assert rp.clean_pred("** Amsterdam") == "Amsterdam"
    assert rp.clean_pred("** New_York_City") == "New_York_City"
    assert rp.clean_pred("UNKNOWN**") == "UNKNOWN"
    text = "ANSWER_PLAIN[X]: Burbank**\n# raw_tail\n**ANSWER_PLAIN[X]: Burbank**\n"
    assert rp.first_pred(text) == "Burbank"
    raw = "**ANSWER_SEALED[ER22_OO_UNIQUE_31]:** Ed952835710d5\n"
    pred, stored = rp.parse("ER22_OO_UNIQUE_31", raw, sealed=True)
    assert pred == "Ed952835710d5"
    assert "Ed952835710d5" in stored.splitlines()[0]
    recovered = rp.preds_from_text(
        "ANSWER_SEALED[ER22_OO_UNIQUE_31]: \n# raw_tail\n**ANSWER_SEALED[ER22_OO_UNIQUE_31]:** Ed952835710d5\n",
        rp.ANS_SEAL,
    )
    assert recovered["ER22_OO_UNIQUE_31"] == "Ed952835710d5"

    legacy = "ANSWER_PLAIN[X]: UNKNOWN\n# raw\n\n"
    assert rp.classify(legacy) == "legacy_empty"
    assert rp.is_final(legacy)  # resuming must not silently overwrite locked replies


def test_headline_cells_contain_no_empty_completions():
    for rel in ("factorial_2x2_iso_harness_replies_gpt56/OPAQUE_AMBIG",
                "entity_rel_2x2_iso_harness_replies_gpt56/OO_AMBIG"):
        kinds = {rp.classify(p.read_text()) for p in (ROOT / "results" / rel).glob("item_*.txt")}
        assert kinds and not kinds & {"legacy_empty", "no_output"}


def test_entity_seal_rejects_distinct_names_sharing_a_seal():
    s = EntitySeal(b"k" * 16)
    s.atom("東京 Tower")
    with pytest.raises(ValueError):
        s.atom("大阪 Tower")


def test_entity_seal_keeps_documented_whitespace_binding():
    s = EntitySeal(b"k" * 16)
    assert s.atom("Michael Eisner") == s.atom("Michael_Eisner")


def test_entity_seal_legacy_mode_reproduces_old_merge():
    s = EntitySeal(b"k" * 16, strict=False)
    assert s.atom("東京 Tower") == s.atom("大阪 Tower")


def test_header_decoy_ablation_build(tmp_path):
    mod = _load("header_decoy_ablation_iso")
    h = mod.build(runs=tmp_path / "runs", harness_path=tmp_path / "h.json")
    assert len(h["arms"]) == 7 and all(len(a["ids"]) == 32 for a in h["arms"].values())
    labels = ("OPAQUE", "AMBIG", "K2", "H5", "NONE", "CYC", "CRV", "ENG", "CURVE", "F22")
    for arm, meta in h["arms"].items():
        assert not any(x in cid for cid in meta["ids"] for x in labels)
        first = (tmp_path / "runs" / arm / "item_0" / "prompt.txt").read_text()
        assert ("\nARM " in first) == (meta["header"] != "NONE")
    for i in range(32):  # OPQ_H5_CYC == locked WIKI-H5 header and CONTEXT
        new = (tmp_path / "runs" / "OPQ_H5_CYC" / f"item_{i}" / "prompt.txt").read_text()
        old = (ROOT / "runs/factorial_2x2_iso/OPAQUE_AMBIG" / f"item_{i}" / "prompt.txt").read_text()
        assert new.split("CONTEXT:", 1)[1] == old.split("CONTEXT:", 1)[1]
        assert new.splitlines()[2] == old.splitlines()[2]
    curve = json.loads((ROOT / "results/ambig_curve_iso_harness.json").read_text())
    assert [c["decoy_hq"]["CRV"] for c in h["cases"]] == [c["decoy_hq"] for c in curve["cases"]]


def test_header_decoy_ablation_score(tmp_path):
    mod = _load("header_decoy_ablation_iso")
    hp = tmp_path / "header_decoy_ablation_iso_harness.json"
    h = mod.build(runs=tmp_path / "runs", harness_path=hp)
    root = tmp_path / f"{hp.stem}_replies_fake"
    for arm, meta in h["arms"].items():
        (root / arm).mkdir(parents=True)
        for i, case in enumerate(h["cases"]):
            cid = meta["ids"][i]
            if arm == "OPQ_NONE_CYC":
                raw = f"ANSWER_PLAIN[{cid}]: {case['gold']}"
            elif i < 4:
                raw = ""
            else:
                raw = f"ANSWER_PLAIN[{cid}]: UNKNOWN"
            (root / arm / f"item_{i}.txt").write_text(rp.parse(cid, raw, sealed=False)[1])
    out = mod.score("fake", harness_path=hp, results_dir=tmp_path)
    assert out["cells"]["OPQ_NONE_CYC"] == {"gold": 32}
    assert out["cells"]["OPQ_H5_CYC"] == {"no_output": 4, "unknown": 28}
    c = next(x for x in out["contrasts"] if (x["a"], x["b"]) == ("OPQ_H5_CYC", "OPQ_NONE_CYC"))
    assert c["n_paired"] == 28
    assert (c["a_only"], c["b_only"]) == (0, 28)
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        mod.score("fake", harness_path=hp, results_dir=tmp_path)
    mod.score("fake", harness_path=hp, results_dir=tmp_path, force=True)


def test_agent_runner_accepts_cursor_api_key(monkeypatch):
    mod = _load("run_iso_agent_harness")
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    monkeypatch.setenv("CURSOR_API_KEY", "crsr_test")
    assert mod.resolve_api_key() == "crsr_test"
    monkeypatch.delenv("CURSOR_API_KEY")
    with pytest.raises(SystemExit):
        mod.resolve_api_key()


def test_agent_runner_canary_does_not_persist_error(tmp_path):
    mod = _load("run_iso_agent_harness")
    out = tmp_path / "item_0.txt"
    with pytest.raises(SystemExit, match="no canary reply was written"):
        mod.settle_canary({"raw": "ERROR: You have an unpaid invoice", "text": "x",
                           "sidecar": {"id": "x"}}, out)
    assert not out.exists()
    assert not out.with_suffix(".json").exists()
    with pytest.raises(SystemExit, match="canary failed"):
        mod.settle_canary({"raw": "ERROR: timeout 90s", "text": "x",
                           "sidecar": {"id": "x"}}, out)
    assert not out.exists()
    mod.settle_canary({"raw": "Burbank", "text": "ANSWER_PLAIN[X]: Burbank\n",
                       "sidecar": {"id": "x"}}, out)
    assert out.exists()


def test_ceiling_lock_tag_ignores_empty_harness_stem(tmp_path):
    mod = _load("score_ceiling_n32_iso")
    (tmp_path / "ceiling_three_arm_n32_iso_harness_replies_gpt56").mkdir()
    legacy = tmp_path / "ceiling_n32_iso_replies_gpt56" / "SEAL_NL"
    legacy.mkdir(parents=True)
    (legacy / "item_0.txt").write_text("ANSWER_SEALED[X]: UNKNOWN\n")
    assert mod.reply_root("gpt56", tmp_path) == tmp_path / "ceiling_n32_iso_replies_gpt56"


def test_ceiling_new_tag_uses_populated_stem_not_empty_legacy(tmp_path):
    mod = _load("score_ceiling_n32_iso")
    stem = tmp_path / "ceiling_three_arm_n32_iso_harness_replies_composer25tx" / "SEAL_NL"
    stem.mkdir(parents=True)
    (stem / "item_0.txt").write_text("ANSWER_SEALED[X]: UNKNOWN\n")
    (tmp_path / "ceiling_n32_iso_replies_composer25tx").mkdir()
    assert "harness_replies" in mod.reply_root("composer25tx", tmp_path).name


def test_lockjson_refuse_does_not_mutate_caller(tmp_path):
    mod = _load("lockjson")
    p = tmp_path / "cell.json"
    mod.write_lock(p, {"tag": "a", "note": "keep"})
    payload = {"tag": "b"}
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        mod.write_lock(p, payload)
    assert payload == {"tag": "b"}


def test_lockjson_refuses_overwrite(tmp_path):
    mod = _load("lockjson")
    p = tmp_path / "cell.json"
    mod.write_lock(p, {"tag": "a", "note": "keep"})
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        mod.write_lock(p, {"tag": "b"})
    mod.write_lock(p, {"tag": "b"}, force=True)
    blob = json.loads(p.read_text())
    assert blob["tag"] == "b" and blob["note"] == "keep"
    assert p.read_text().endswith("\n")


def test_transcript_kind_splits_answer_only_from_dump():
    assert rp.transcript_kind("ANSWER_SEALED[X]: UNKNOWN\n") == "answer_only"
    assert rp.transcript_kind("ANSWER_SEALED[X]: Y\n# raw_tail\nY\n") == "transcript"
    assert rp.transcript_kind("ANSWER_SEALED[X]: Y\n# raw_tail 2-hop via Z\n") == "short_tail"
    assert rp.transcript_kind("# induce_mut tag=composer25 method=sealed_demo_binding\n") == "induce"


def test_agent_runner_detects_unpaid_invoice():
    mod = _load("run_iso_agent_harness")
    assert mod._billing_blocked("ERROR: You have an unpaid invoice Visit cursor.com/dashboard")
    assert not mod._billing_blocked("ANSWER_PLAIN[X]: Burbank")
    err = "ERROR: You have an unpaid invoice\n"
    assert not rp.is_final(err)


def test_error_in_raw_tail_does_not_unfinalize():
    text = "ANSWER_PLAIN[X]: Burbank\n# raw_tail\n... ERROR: ignored in transcript ...\n"
    assert rp.classify(text) == "explicit_answer"
    assert rp.is_final(text)
    assert not rp.is_final("ERROR: timeout 90s\n")


def test_openai_runner_requires_tag_and_rejects_arm_as_tag():
    mod = _load("run_openai_iso_harness")
    p = mod.build_parser()
    ns = p.parse_args([
        str(ROOT / "results/factorial_2x2_iso_harness.json"), "gpt56abl",
        "--max-completion-tokens", "4096",
    ])
    assert ns.tag == "gpt56abl"
    assert ns.max_completion_tokens == 4096
    assert p.get_default("max_completion_tokens") == 512
    with pytest.raises(SystemExit, match="arm name"):
        mod.parse_cli([str(ROOT / "results/factorial_2x2_iso_harness.json"), "OPAQUE_AMBIG"])


def test_factorial_scorer_missing_arm_is_nr_not_zero(tmp_path):
    import shutil
    src = ROOT / "results/factorial_2x2_iso_harness.json"
    shutil.copy(src, tmp_path / "factorial_2x2_iso_harness.json")
    (tmp_path / "factorial_2x2_iso_harness_replies_fake").mkdir()
    mod = _load("score_factorial_2x2")
    out = mod.score("fake", results_dir=tmp_path)
    assert all(c["score"] == "n.r." and c["missing"] == 32 for c in out["summary"].values())
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        mod.score("fake", results_dir=tmp_path)


def test_header_decoy_composer_grok_replies_are_not_errors():
    for tag in ("composer25abl", "grok45abl"):
        files = list((ROOT / "results" / f"header_decoy_ablation_iso_harness_replies_{tag}").glob("*/item_*.txt"))
        assert len(files) == 224, tag
        kinds = {rp.classify(p.read_text()) for p in files}
        assert "error" not in kinds, (tag, kinds)

