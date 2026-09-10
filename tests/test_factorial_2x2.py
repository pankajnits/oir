import importlib.util
import json
from pathlib import Path

from oir.adapters import load_json_records

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "factorial_2x2_iso", ROOT / "harness" / "factorial_2x2_iso.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_unique_vs_ambig_hop_counts():
    recs = load_json_records(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    a, b = recs[0], recs[1]
    u = mod.unique_edges(a, b)
    g = mod.ambig_edges(a, b)
    assert len(mod.two_hops(u, a["person"])) == 1
    assert len(mod.two_hops(g, a["person"])) == 2
    assert mod.two_hops(u, a["person"])[0][2] == a["hq"]


def test_perm_and_curve_topology():
    spec2 = importlib.util.spec_from_file_location(
        "ambig_curve_iso", ROOT / "harness" / "ambig_curve_iso.py"
    )
    cv = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(cv)
    recs = load_json_records(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    row = recs[0]
    decoys = [
        {"company": f"C{j}", "hq": f"City{j}"}
        for j in range(4)
    ]
    for k in (1, 2, 3, 4, 5):
        e = cv.edges_for_k(row, decoys, k)
        assert len(cv.two_hops(e, row["person"])) == k
    spec3 = importlib.util.spec_from_file_location(
        "perm_2x2_iso", ROOT / "harness" / "perm_2x2_iso.py"
    )
    pm = importlib.util.module_from_spec(spec3)
    spec3.loader.exec_module(pm)
    s = pm.PermSeal(pm.random.Random(0))
    a, b = s.atom("works_at"), s.atom("headquartered_in")
    assert a.startswith("E") and a != b and s.atom("works_at") == a


def test_alpha_tokens_not_hmac_shaped():
    spec_a = importlib.util.spec_from_file_location(
        "alpha_2x2_iso", ROOT / "harness" / "alpha_2x2_iso.py"
    )
    am = importlib.util.module_from_spec(spec_a)
    spec_a.loader.exec_module(am)
    s = am.AlphaSeal(am.random.Random(0))
    toks = [s.atom(x) for x in ("works_at", "headquartered_in", "partner_of")]
    assert len(set(toks)) == 3
    assert all(len(t) == 12 and not am.HMAC_SHAPE.match(t) for t in toks)
    h = json.loads((ROOT / "results/entity_rel_2x2_iso_harness.json").read_text())
    prompt = (ROOT / "runs/entity_rel_2x2_iso/OO_UNIQUE/item_0/prompt.txt").read_text()
    case0 = h["cases"][0]
    assert case0["gold"] in prompt  # unique-path CONTEXT contains the sealed answer node
    assert case0["hq"] not in prompt and case0["person"] not in prompt
    assert "What city is the headquarters" in prompt


def test_dualpath_wikimovies_matched_vs_novel():
    matched = (ROOT / "runs/dualpath_wikimovies_iso/MATCHED/item_0/prompt.txt").read_text()
    novel = (ROOT / "runs/dualpath_wikimovies_iso/NOVEL/item_0/prompt.txt").read_text()
    assert "DEMO 0:" in matched and "--- QUIZ ---" in matched
    assert "appeared_in_quiz" not in matched
    # novel quiz uses renamed relations; demos still use starred_in/directed_by
    assert "START " in novel


def test_metaqa_official_keeps_bracketed_start():
    h = json.loads((ROOT / "results/metaqa_official_iso_harness.json").read_text())
    qeng = (ROOT / "runs/metaqa_official_iso/OPAQUE_REL_QENG/item_0/prompt.txt").read_text()
    qh = (ROOT / "runs/metaqa_official_iso/OPAQUE_REL_QHASH/item_0/prompt.txt").read_text()
    start = h["cases"][0]["start"]
    assert f"[{start}]" in qeng and f"[{start}]" in qh
    assert "directed" in qeng.lower() or "starred" in qeng.lower()
    # Condition B should not leave the cue verb in the clear
    assert "directed" not in qh.lower().split("CONTEXT:")[0]


def test_wikimovies_n100_qhash_no_verb_leak():
    """Read committed MUT files. Do not call build() (that rewrites the lock)."""
    root = ROOT / "runs" / "metaqa_2x2_people_n100_qhash_iso"
    leaks = ("directed", "starred", "written", "writer", "director")
    paths = list(root.rglob("prompt.txt"))
    assert len(paths) == 300
    for p in paths:
        low = p.read_text().lower()
        for w in leaks:
            assert w not in low, (p, w)
    h = json.loads((ROOT / "results/metaqa_2x2_people_n100_qhash_iso_harness.json").read_text())
    assert h["n"] == 100
    prompt = (root / "OPAQUE_AMBIG" / "item_0" / "prompt.txt").read_text()
    actor = h["cases"][0]["actor"]
    assert f"[{actor}]" in prompt
    assert "two 2-hops from start" in prompt
    assert "director vs writer" not in prompt.lower()
