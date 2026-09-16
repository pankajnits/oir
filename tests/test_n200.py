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


def test_k3_n200_does_not_replace_locks():
    """Headline n=200 tags stay 38/200 and 134; k=3 is extra snapshots."""
    lock = json.loads((ROOT / "results/factorial_2x2_iso_n200_gpt56n200.json").read_text())
    assert lock["summary"]["OPAQUE_AMBIG"]["score"] == "38/200"
    hdr = json.loads((ROOT / "results/header_decoy_ablation_iso_n200_gpt56n200h512.json").read_text())
    assert hdr["cells"]["OPQ_H5_CYC"]["gold"] == 134
    r2 = json.loads((ROOT / "results/factorial_2x2_iso_n200_gpt56n200k3r2.json").read_text())
    r3 = json.loads((ROOT / "results/factorial_2x2_iso_n200_gpt56n200k3r3.json").read_text())
    assert "does not replace" in r2.get("note", "").lower()
    assert "does not replace" in r3.get("note", "").lower()
    assert r2["summary"]["OPAQUE_AMBIG"]["score"] == "46/200"
    assert r3["summary"]["OPAQUE_AMBIG"]["score"] == "43/200"
    assert r2["summary"]["OPAQUE_AMBIG"]["unknown"] == 144
    assert r3["summary"]["OPAQUE_AMBIG"]["unknown"] == 142
    assert r2["summary"]["OPAQUE_AMBIG"]["decoy"] == 10
    assert r3["summary"]["OPAQUE_AMBIG"]["decoy"] == 15
    assert r2["summary"]["OPAQUE_UNIQUE"]["score"] == "n.r."
    h2 = json.loads((ROOT / "results/header_decoy_ablation_iso_n200_gpt56n200h512k3r2.json").read_text())
    h3 = json.loads((ROOT / "results/header_decoy_ablation_iso_n200_gpt56n200h512k3r3.json").read_text())
    assert "does not replace" in h2.get("note", "").lower()
    assert "does not replace" in h3.get("note", "").lower()
    assert h2["cells"]["OPQ_H5_CYC"]["gold"] == 130
    assert h3["cells"]["OPQ_H5_CYC"]["gold"] == 127
    assert h2["cells"]["OPQ_H5_CYC"].get("no_output", 0) == 0
    assert h3["cells"]["OPQ_H5_CYC"].get("no_output", 0) == 0
    assert h3["cells"]["OPQ_H5_CYC"].get("other", 0) == 1
    for arm, cell in h2["cells"].items():
        if arm != "OPQ_H5_CYC":
            assert cell.get("missing") == 200, arm
    sidecar = json.loads(
        (ROOT / "results/factorial_2x2_iso_n200_harness_replies_gpt56n200k3r2" / "OPAQUE_AMBIG" / "item_0.json").read_text()
    )
    assert sidecar.get("returned_model") == "gpt-5.6-sol"
    n32 = json.loads((ROOT / "results/factorial_2x2_iso_gpt56.json").read_text())
    assert n32["summary"]["OPAQUE_AMBIG"]["score"] == "6/32"


def test_n200_constant_decoy_is_curve_not_cogent():
    """n=200 CRV is curve_decoy (San_Jose x199, London x1), not Cogent→DC."""
    h = json.loads((ROOT / "results/header_decoy_ablation_iso_n200_harness.json").read_text())
    tails = Counter(c["decoy_hq"]["CRV"] for c in h["cases"])
    assert tails == {"San_Jose": 199, "London": 1}
    assert all(c["gold"] != c["decoy_hq"]["CRV"] for c in h["cases"])
    assert all(c["gold"] != c["decoy_hq"]["CYC"] for c in h["cases"])
    n32 = json.loads((ROOT / "results/header_decoy_ablation_iso_harness.json").read_text())
    assert all(c["gold"] != c["decoy_hq"]["CYC"] for c in n32["cases"])
    assert all(c["gold"] != c["decoy_hq"]["CRV"] for c in n32["cases"])
    assert {c["decoy_hq"]["CRV"] for c in n32["cases"]} == {"Washington_DC"}
    n32_prompt = (ROOT / "runs/header_decoy_ablation_iso/OPQ_NONE_CRV/item_0/prompt.txt").read_text()
    assert "Cogent_Communications" in n32_prompt
    n200_prompt = (ROOT / "runs/header_decoy_ablation_iso_n200/OPQ_NONE_CRV/item_0/prompt.txt").read_text()
    assert "Cogent" not in n200_prompt
    tex_path = ROOT / "paper/arxiv_upload/main.tex"
    if tex_path.is_file():
        tex = tex_path.read_text()
        assert r"San\_Jose ${\times}199$" in tex
        assert r"constant $=$ one Cogent" not in tex


def test_openai_k_sweep_is_29_29_28_27_28():
    s = json.loads((ROOT / "results/ambig_curve_iso_gpt56.json").read_text())["summary"]
    assert [s[f"K{k}"]["score"] for k in range(1, 6)] == [
        "29/32", "29/32", "28/32", "27/32", "28/32",
    ]


ARM_LINES = {
    "ENG_UNIQUE": "ARM ENG_UNIQUE: English relations; one 2-hop from start.",
    "ENG_AMBIG": "ARM ENG_AMBIG: English relations; two 2-hops from start.",
    "OPAQUE_UNIQUE": "ARM OPAQUE_UNIQUE: opaque relations, English entities; one 2-hop from start.",
    "OPAQUE_AMBIG": "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start.",
    "OPAQUE_AMBIG_PLAN": "ARM OPAQUE_AMBIG_PLAN: same graph as OPAQUE_AMBIG plus explicit relation sequence.",
}


def test_wiki_h5_named_arm_lines_match_harness():
    for stem in ("factorial_2x2_iso", "factorial_2x2_iso_n200"):
        for arm, line in ARM_LINES.items():
            text = (ROOT / "runs" / stem / arm / "item_0" / "prompt.txt").read_text()
            assert line in text, (stem, arm)


def test_curve_decoy_skips_same_company_hq_person():
    import sys

    sys.path.insert(0, str(ROOT / "harness"))
    from header_decoy_ablation_iso import curve_decoy  # noqa: E402

    recs = load_json_records(WIKI)
    gold = recs[0]
    decoy = curve_decoy(gold, recs)
    assert decoy["company"] != gold["company"]
    assert decoy["hq"] != gold["hq"]
    assert decoy["person"] != gold["person"]
    assert decoy["hq"] == "London"


def test_n200_no_arm_cyclic_english_vs_opaque_mcnemar_25_vs_2():
    import sys
    from math import comb

    sys.path.insert(0, str(ROOT / "harness"))
    from header_decoy_ablation_iso import classify, first_pred  # noqa: E402

    h = json.loads((ROOT / "results/header_decoy_ablation_iso_n200_harness.json").read_text())
    reply = ROOT / "results/header_decoy_ablation_iso_n200_harness_replies_gpt56n200abl"
    eng_only = opq_only = 0
    for i, case in enumerate(h["cases"]):
        hits = {}
        for arm in ("ENG_NONE_CYC", "OPQ_NONE_CYC"):
            text = (reply / arm / f"item_{i}.txt").read_text()
            kind, pred = classify(text), first_pred(text)
            incomplete = kind in ("error", "no_output", "legacy_empty")
            assert not incomplete
            hits[arm] = pred == case["gold"]
        if hits["ENG_NONE_CYC"] and not hits["OPQ_NONE_CYC"]:
            eng_only += 1
        elif hits["OPQ_NONE_CYC"] and not hits["ENG_NONE_CYC"]:
            opq_only += 1
    assert (eng_only, opq_only) == (25, 2)
    n = eng_only + opq_only
    p = min(1.0, 2 * sum(comb(n, j) for j in range(min(eng_only, opq_only) + 1)) / 2**n)
    assert abs(p - 5.65e-6) < 2e-8


def test_paper_tex_named_arm_vs_no_arm_wording():
    tex_path = ROOT / "paper/arxiv_upload/main.tex"
    if not tex_path.is_file():
        return
    tex = tex_path.read_text()
    assert "varies only relation" not in tex
    assert "recover joins rather than guesses" not in tex
    assert r"McNemar $25$ vs.\ $2$" in tex
    assert r"H5 vs.\ no-ARM on constant decoys is McNemar $4$ vs.\ $111$" in tex
    assert r"does not share company" in tex
    assert "ARM ENG\\_UNIQUE" in tex or r"\texttt{ENG\_UNIQUE}" in tex
    assert "512 tokens" in tex
    assert "cyclic-decoy English two-path" in tex
    h8 = tex[tex.find("H8. Prompt surface") : tex.find("H8. Prompt surface") + 400]
    assert "95" not in h8
    assert "4" in h8 and "111" in h8
    assert "Without Relation Names" in tex
    assert "Without Lexical Cues" not in tex
    assert "74 become" in tex and "21 take the constant decoy" in tex
    assert r"Two-path K2 and no-ARM were not run at 512" in tex
    assert tex.count("Two-path K2 and no-ARM were not run at 512") == 2
    assert "K2 and no-ARM were not run at 512" in tex
    assert r"hashed-id no-ARM $200/200$ at 512 tokens" in tex
    assert r"hashed-id no-ARM unique $200/200$ at 512 tokens" in tex
    assert "municipality of the Czech Republic" in tex
    assert "place with town rights" in tex
    assert "city of Japan" not in tex
    assert "city in Canada" not in tex
    assert r"\texttt{OE\_UNIQUE}" in tex
    assert "Hypothesis H5 in this table" in tex
    assert "2 same-type 2-hop(s) from start" in tex
    assert "Sign-flip of the two-path opacity contrast" in tex
    assert "Sign-flip of the H5 interaction" not in tex
    assert r"H5 vs.\ no-ARM on cyclic decoys is McNemar $6$ vs.\ $51$" in tex
    assert r"$p{=}5.7{\times}10^{-10}$" in tex
    assert "announcing two 2-hops is not what" in tex
    assert "named-arm phenomenon" not in tex
    assert "is not a three-family law" not in tex
    assert "item-level interaction contrast" in tex
    assert r"$6/3/23$" in tex
    assert "graph size fixed" not in tex
    assert r"$n{=}6$ batch" in tex
    assert ("/" + "Users/") not in tex
    assert "15~September named-arm lock" in tex
    assert r"Headline $n{=}200$ is the \texttt{gpt56n200}/\texttt{gpt56n200h512} lock" not in tex
    cap = tex[tex.find("fig3_dualpath.png") : tex.find(r"\label{fig:dualpath}")]
    assert "balanced" not in cap.lower()
    assert "matched" in cap


def test_unique_no_arm_same_context_and_openai_lock():
    def ctx(path: Path) -> str:
        return path.read_text().split("CONTEXT:\n", 1)[1].rstrip("\n")

    n32_named = ROOT / "runs/factorial_2x2_iso/OPAQUE_UNIQUE/item_0/prompt.txt"
    n32_none = ROOT / "runs/unique_no_arm_iso/OPQ_NONE_UNI/item_0/prompt.txt"
    assert ctx(n32_named) == ctx(n32_none)
    body = n32_none.read_text()
    assert "ARM " not in body
    assert "OPAQUE_UNIQUE" not in body
    n200_named = ROOT / "runs/factorial_2x2_iso_n200/OPAQUE_UNIQUE/item_0/prompt.txt"
    n200_none = ROOT / "runs/unique_no_arm_iso_n200/OPQ_NONE_UNI/item_0/prompt.txt"
    assert ctx(n200_named) == ctx(n200_none)
    n32 = json.loads((ROOT / "results/unique_no_arm_iso_gpt56uninone.json").read_text())
    assert n32["summary"]["OPQ_NONE_UNI"]["score"] == "27/32"
    assert n32["summary"]["OPQ_NONE_UNI"]["unknown"] == 3
    noncity = {
        "Broadway",
        "NRK_Marienlyst",
        "Fox_Plaza",
        "CNN_Center",
        "Lod_Railway_Station",
        "New_Jersey",
    }
    city = [r for r in n32["rows"] if r["gold"] not in noncity]
    assert len(city) == 26 and all(r["ok"] for r in city)
    n200 = json.loads((ROOT / "results/unique_no_arm_iso_n200_gpt56n200uninone.json").read_text())
    assert n200["summary"]["OPQ_NONE_UNI"]["score"] == "200/200"
    sidecar = json.loads(
        (
            ROOT
            / "results/unique_no_arm_iso_n200_harness_replies_gpt56n200uninone"
            / "OPQ_NONE_UNI"
            / "item_0.json"
        ).read_text()
    )
    assert sidecar["request"]["max_completion_tokens"] == 512
    assert "reasoning_effort" not in sidecar["request"]
    named = json.loads((ROOT / "results/factorial_2x2_iso_n200_gpt56n200.json").read_text())
    assert named["summary"]["OPAQUE_UNIQUE"]["score"] == "200/200"
