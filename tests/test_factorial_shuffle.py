"""Gold/decoy listing shuffle: read committed files. Do not call build()."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from oir import EntitySeal

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "harness" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_shuffle_does_not_touch_primary_lock():
    primary = (ROOT / "runs/factorial_2x2_iso/OPAQUE_AMBIG/item_0/prompt.txt").read_text()
    h = json.loads((ROOT / "results/factorial_2x2_iso_shuffle_harness.json").read_text())
    after = (ROOT / "runs/factorial_2x2_iso/OPAQUE_AMBIG/item_0/prompt.txt").read_text()
    assert after == primary
    assert h["n"] == 32
    assert h["n_gold_first"] == 16
    assert h["n_decoy_first"] == 16
    assert h["primary_lock_untouched"] == "runs/factorial_2x2_iso/"
    assert sum(1 for c in h["cases"] if c["gold_first"]) == 16


def test_shuffle_is_order_only_same_hmac():
    fact = _load("factorial_2x2_iso")
    h = json.loads((ROOT / "results/factorial_2x2_iso_shuffle_harness.json").read_text())
    sealer = EntitySeal(fact.item_key(0))
    works = sealer.atom("works_at")
    primary = (ROOT / "runs/factorial_2x2_iso/OPAQUE_AMBIG/item_0/prompt.txt").read_text()
    shuffled = (ROOT / h["arms"]["OPAQUE_AMBIG"]["item_paths"][0]).read_text()
    assert works in primary and works in shuffled
    assert "gold-first" not in shuffled
    assert "decoy-first" not in shuffled
    assert "PATH_QUERY" not in shuffled
    case0 = h["cases"][0]
    ctx = shuffled.split("CONTEXT:", 1)[1]
    first_city_line = [ln for ln in ctx.splitlines() if ln.strip()][1]
    if case0["gold_first"]:
        assert case0["hq"] in first_city_line
        assert ctx.find(case0["hq"]) < ctx.find(case0["decoy_hq"])
    else:
        assert case0["decoy_hq"] in first_city_line
        assert ctx.find(case0["decoy_hq"]) < ctx.find(case0["hq"])
    decoy_item = next(c for c in h["cases"] if not c["gold_first"])
    dctx = (ROOT / h["arms"]["OPAQUE_AMBIG"]["item_paths"][decoy_item["i"]]).read_text()
    assert dctx.find(decoy_item["decoy_hq"]) < dctx.find(decoy_item["hq"])
    eng = (ROOT / h["arms"]["ENG_AMBIG"]["item_paths"][decoy_item["i"]]).read_text()
    assert "partner_of" in eng
    assert eng.find(decoy_item["decoy_hq"]) < eng.find(decoy_item["hq"])
