"""n=200 freeze is real, typed, and does not rewrite n=32 locks."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from oir.adapters import load_json_records

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "data/real/wikidata_ceo_hops_n200.json"
VERIFY = ROOT / "results/wikidata_ceo_hops_n200_verify.json"
N32_HARNESS = ROOT / "results/factorial_2x2_iso_harness.json"
N200_HARNESS = ROOT / "results/factorial_2x2_iso_n200_harness.json"


def test_n32_lock_untouched():
    h = json.loads(N32_HARNESS.read_text())
    assert h["n"] == 32
    assert h["source"] == "data/real/wikidata_ceo_hops_v2.json"
    assert (ROOT / "runs/factorial_2x2_iso/OPAQUE_AMBIG/item_0/prompt.txt").is_file()


def test_wiki_n200_freeze_is_city_typed_and_unique():
    recs = load_json_records(WIKI)
    assert len(recs) == 200
    people = [r["person"] for r in recs]
    companies = [r["company"] for r in recs]
    assert len(set(people)) == 200
    assert len(set(companies)) == 200
    for r in recs:
        assert r["person_qid"].startswith("Q")
        assert r["company_qid"].startswith("Q")
        assert r["hq_qid"].startswith("Q")
        assert r["hq_p31"].startswith("Q")
        assert r["person"] and r["company"] and r["hq"]
        assert " " not in r["person"]
    hq_n = Counter(r["hq"] for r in recs)
    assert max(hq_n.values()) <= 3
    n = len(recs)
    for i, r in enumerate(recs):
        nxt = recs[(i + 1) % n]
        assert nxt["hq"] != r["hq"] and nxt["person"] != r["person"]


def test_wiki_n200_live_verify_lock():
    v = json.loads(VERIFY.read_text())
    assert v["n"] == 200
    assert v["p169_p159_ok"] == 200
    assert v["city_p31_ok"] == 200
    assert v["p169_p159_missing"] == []
    assert v["city_p31_missing"] == []


def test_wiki_h5_n200_prompts_and_ceiling():
    h = json.loads(N200_HARNESS.read_text())
    assert h["n"] == 200
    assert h["source"] == "data/real/wikidata_ceo_hops_n200.json"
    assert h["n32_untouched"] == "runs/factorial_2x2_iso/"
    assert len(h["cases"]) == 200
    prompt = (ROOT / "runs/factorial_2x2_iso_n200/OPAQUE_AMBIG/item_0/prompt.txt").read_text()
    case0 = h["cases"][0]
    assert case0["person"] in prompt
    assert case0["gold"] in prompt  # English entity in CONTEXT
    assert f"F200_OPAQUE_AMBIG_0" in prompt
    assert "two 2-hops from start" in prompt
    for arm in h["arms"]:
        assert len(list((ROOT / "runs/factorial_2x2_iso_n200" / arm).glob("item_*/prompt.txt"))) == 200


def test_header_n200_same_hmac_context_as_named_arm():
    named = (ROOT / "runs/factorial_2x2_iso_n200/OPAQUE_AMBIG/item_0/prompt.txt").read_text()
    hashed = (ROOT / "runs/header_decoy_ablation_iso_n200/OPQ_H5_CYC/item_0/prompt.txt").read_text()
    def ctx(s: str) -> str:
        return s.split("CONTEXT:\n", 1)[1]
    assert ctx(named) == ctx(hashed)
    assert "F200_OPAQUE_AMBIG_0" in named
    assert "F200_OPAQUE_AMBIG_0" not in hashed
    assert "H200_" in hashed


def test_wiki_h5_n200_openai_lock():
    h = json.loads((ROOT / "results/factorial_2x2_iso_n200_gpt56n200.json").read_text())
    assert h["n"] == 200
    assert h["summary"]["OPAQUE_UNIQUE"]["score"] == "200/200"
    assert h["summary"]["ENG_UNIQUE"]["score"] == "200/200"
    assert h["summary"]["ENG_AMBIG"]["score"] == "199/200"
    assert h["summary"]["OPAQUE_AMBIG"]["score"] == "38/200"
    assert h["summary"]["OPAQUE_AMBIG"]["unknown"] == 151
    assert h["summary"]["OPAQUE_AMBIG"]["decoy"] == 11
    assert h["summary"]["OPAQUE_AMBIG_PLAN"]["score"] == "200/200"
    hdr = json.loads((ROOT / "results/header_decoy_ablation_iso_n200_gpt56n200h512.json").read_text())
    assert hdr["cells"]["OPQ_H5_CYC"]["gold"] == 134
    for arm, cell in hdr["cells"].items():
        if arm != "OPQ_H5_CYC":
            assert cell.get("missing") == 200, arm
    abl = json.loads((ROOT / "results/header_decoy_ablation_iso_n200_gpt56n200abl.json").read_text())
    assert abl["cells"]["OPQ_H5_CYC"]["gold"] == 129
    assert abl["cells"]["OPQ_H5_CRV"]["gold"] == 44
    oo = json.loads((ROOT / "results/entity_rel_2x2_iso_n200_gpt56n200.json").read_text())
    assert oo["summary"]["OO_UNIQUE"]["score"] == "200/200"
    assert oo["summary"]["OO_AMBIG"]["score"] == "12/200"
    ceil = json.loads((ROOT / "results/ceiling_three_arm_n200_iso_gpt56n200.json").read_text())
    assert ceil["summary"]["SEAL_PROG"]["score"] == "200/200"
    assert ceil["summary"]["SEAL_NL"]["score"] == "0/200"
    assert ceil["summary"]["SEAL_NL"]["missing"] == 0


def test_movie_n200_includes_n100_prefix():
    n100 = json.loads((ROOT / "data/metaqa/oir_2hop_people_n100.json").read_text())["items"]
    n200 = json.loads((ROOT / "data/metaqa/oir_2hop_people_n200.json").read_text())["items"]
    assert len(n200) == 200
    assert n200[:100] == n100
    assert len({r["actor"] for r in n200}) == 200
    h = json.loads((ROOT / "results/metaqa_2x2_people_n200_iso_harness.json").read_text())
    assert h["n"] == 200
    assert (ROOT / "runs/metaqa_2x2_people_n100_iso/OPAQUE_AMBIG/item_0/prompt.txt").is_file()
    a = json.loads((ROOT / "results/metaqa_2x2_people_n200_iso_gpt56n200.json").read_text())
    b = json.loads((ROOT / "results/metaqa_2x2_people_n200_qhash_iso_gpt56n200.json").read_text())
    assert a["summary"]["OPAQUE_AMBIG"]["score"] == "122/200"
    assert b["summary"]["OPAQUE_AMBIG"]["score"] == "7/200"
    dual = json.loads((ROOT / "results/dualpath_wikimovies_iso_n200_gpt56n200.json").read_text())
    assert dual["summary"]["MATCHED"]["score"] == "200/200"
    assert dual["summary"]["NOVEL"]["score"] == "2/200"


def test_shuffle_n200_openai_gold_first_split():
    h = json.loads((ROOT / "results/factorial_2x2_iso_shuffle_n200_harness.json").read_text())
    s = json.loads((ROOT / "results/factorial_2x2_iso_shuffle_n200_gpt56n200.json").read_text())
    assert s["summary"]["OPAQUE_AMBIG"]["score"] == "59/200"
    gold_first = {c["i"] for c in h["cases"] if c["gold_first"]}
    assert len(gold_first) == 100
    oa = [r for r in s["rows"] if r["arm"] == "OPAQUE_AMBIG"]
    assert len(oa) == 200
    gf = sum(1 for r in oa if r["ok"] and int(r["id"].rsplit("_", 1)[1]) in gold_first)
    df = sum(1 for r in oa if r["ok"] and int(r["id"].rsplit("_", 1)[1]) not in gold_first)
    assert gf == 25 and df == 34
