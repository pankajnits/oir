#!/usr/bin/env python3
"""Prove the layer mechanism without an LLM (engine ceiling + leak floor).

Paper cells this encodes:
  - Names stay out of the LLM prompt (lexicon hiding).
  - NOBIND splits spaced names (start ∉ V(G)).
  - LAYER binds START, HMAC-seals Q, PATH/JOIN is executable by SealRouter.
  - Per-call keys: same plaintext → different seals across calls.
  - Unseal on this side recovers plaintext.

LLM MUTs (composer-2.5/GPT 6/6) remain in results/seal_layer*.json — not faked here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir.layer import MiddleLayer, leak_check
from oir.adapters import load_ceo_hq_graph

COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]


def country_of(hq: str) -> str:
    return COUNTRIES[sum(map(ord, hq)) % len(COUNTRIES)]


def prove_ceo_vault() -> dict:
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    row, decoy = graph.records[0], graph.records[1]
    person, company, hq = row["person"], row["company"], row["hq"]
    country = country_of(hq)
    display = person.replace("_", " ")
    app_q = f"What is the country of {display}?"

    layer = MiddleLayer()
    vault = {
        "employees": [
            {"id": decoy["person"], "employer": decoy["company"]},
            {"id": person, "employer": company},
        ],
        "orgs": [
            {"id": decoy["company"], "hq": {"city": decoy["hq"], "country": country_of(decoy["hq"])}},
            {"id": company, "hq": {"city": hq, "country": country}},
        ],
    }
    k = {n: layer.atom(n) for n in ("employees", "orgs", "id", "employer", "hq", "country")}
    start = layer.atom(person)
    steps = [
        f"In array {k['employees']}, match {k['id']} = START, take {k['employer']}.",
        f"In array {k['orgs']}, match {k['id']} = that employer, take {k['hq']}.{k['country']}.",
    ]
    call = layer.call(
        cid="PROVE_LAYER_0",
        app_question=app_q,
        names=[person],
        vault=vault,
        join_steps=steps,
        gold_plain=country,
        extra_leak_names=[company, hq, display, decoy["person"].replace("_", " ")],
    )
    # Engine ceiling on the same seals (not the LLM).
    triples = [
        (person, "employer", company),
        (company, "country", country),
        (decoy["person"], "employer", decoy["company"]),
        (decoy["company"], "country", country_of(decoy["hq"])),
    ]
    engine = layer.execute_path(triples, person, ["employer", "country"])
    nobind_q = layer.nobind_question(app_q)
    other = layer.new_call()
    return {
        "app_q": app_q,
        "llm_q": call.sealed_question,
        "start_in_layer_q": call.start in call.sealed_question,
        "start_in_nobind_q": start in nobind_q,
        "plaintext_in_llm_prompt": call.leaked,
        "engine_ok": engine == [call.gold_seal],
        "unseal_ok": layer.unseal(call.gold_seal) == country,
        "per_call_keys_differ": layer.atom(person) != other.atom(person),
        "english_what_in_llm_q": "What" in call.sealed_question,
        "claim": "Lexicon hiding. Not IND-CPA.",
    }


def prove_2wiki_shape() -> dict:
    """Real 2Wiki-shaped hop: bind film name, PATH over sealed edges."""
    layer = MiddleLayer()
    start = "Beat Girl"
    app_q = "Where was the place of death of the director of film Beat Girl?"
    triples = [
        ("Beat Girl", "director", "Edmond T. Greville"),
        ("Edmond T. Greville", "place of death", "Nice"),
        ("Ronnie Rocket", "director", "David Lynch"),
        ("David Lynch", "place of birth", "Missoula"),
    ]
    call = layer.call(
        cid="PROVE_REAL_0",
        app_question=app_q,
        names=[start],
        triples=triples,
        rels=["director", "place of death"],
        gold_plain="Nice",
        extra_leak_names=["Edmond T. Greville", "David Lynch", "Missoula"],
    )
    engine = layer.execute_path(triples, start, ["director", "place of death"])
    nobind = layer.nobind_question(app_q)
    return {
        "app_q": app_q,
        "start_in_layer_q": call.start in call.sealed_question,
        "start_in_nobind_q": layer.atom(start) in nobind,
        "leaked": call.leaked,
        "engine_ok": engine == [call.gold_seal],
        "unseal_ok": layer.unseal(call.gold_seal) == "Nice",
    }


def main():
    ceo = prove_ceo_vault()
    wiki = prove_2wiki_shape()
    ok = (
        not ceo["plaintext_in_llm_prompt"]
        and ceo["start_in_layer_q"]
        and not ceo["start_in_nobind_q"]
        and ceo["engine_ok"]
        and ceo["unseal_ok"]
        and ceo["per_call_keys_differ"]
        and not ceo["english_what_in_llm_q"]
        and wiki["engine_ok"]
        and wiki["unseal_ok"]
        and not wiki["leaked"]
        and wiki["start_in_layer_q"]
        and not wiki["start_in_nobind_q"]
    )
    out = {"ok": ok, "ceo": ceo, "real_2wiki_shape": wiki}
    path = ROOT / "results" / "prove_layer.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("wrote", path)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
