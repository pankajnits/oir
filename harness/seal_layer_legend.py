#!/usr/bin/env python3
"""Layer + schema, no JOIN: can the model pick the hop from key meanings?

Small: CEO nested JSON (person → employer → hq.country), city is the trap.
  JOIN    — sealed Q + sealed keys/values + JOIN (known restore)
  LEGEND  — same blob + English→sealed-key schema; no JOIN
  NOLEG   — same blob; no schema; no JOIN

Keys are HMAC(JSONKEY:name) so the sealed question word "country" does not
equal the JSON key. The schema is the only map from meaning → key.

Not confidentiality. Isolation, per-item HMAC. Seed 20260826.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program
from oir.adapters import load_ceo_hq_graph
from oir.layer import bind_span
from use_case_complex import render_complex, world_hr, world_oncall, world_ticket
from wilson_cis import locked_score, wilson
from grev1_fullq_prog import KEYS, country_of, nest, seal_question
from paths import repo_rel

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "seal_layer_legend"
SEED_SMALL = 20260826
SEED_COMPLEX = 20260827
N = 6
ENGLISH_Q = re.compile(r"\b(What|Which|country|the|of|is|HQ|city|department)\b")


def _small_paths(n: int) -> tuple[Path, Path]:
    """Keep locked n=6 prompts/JSON; larger n writes a sibling suite."""
    if n == N:
        return RUNS / "small", RESULTS / "seal_layer_legend_small_harness.json"
    return RUNS / f"small_n{n}", RESULTS / f"seal_layer_legend_small_n{n}_harness.json"
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def pack(cid: str, header: str, q: str, extra: str, ctx: str) -> str:
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. Do not open other files.",
            f"Format: ANSWER_SEALED[{cid}]: <seal_or_UNKNOWN>",
            "If more than one reading is possible, output UNKNOWN.",
            "",
            header,
            "",
            f"##### ID {cid} #####",
            "QUESTION (token-HMAC'd):",
            q,
            "",
            extra,
            "CONTEXT:",
            ctx,
            "",
        ]
    )


def leak_check(prompt: str, *names: str) -> bool:
    return any(n and n in prompt for n in names)


def walk_json(employees, orgs, k, start: str) -> str:
    emp = next(x for x in employees if x[k["id"]] == start)
    company = emp[k["employer"]]
    org = next(x for x in orgs if x[k["id"]] == company)
    return org[k["hq"]][k["country"]]


def legend_block(k: dict[str, str]) -> str:
    lines = ["KEY_SCHEMA (English name → sealed JSON key):"]
    for name in KEYS:
        lines.append(f"{name} = {k[name]}")
    lines.append("Use the schema to read CONTEXT. No JOIN is given. Return one sealed atom.")
    return "\n".join(lines)


def meta_block(k: dict[str, str]) -> str:
    """English how-to + bilingual schema. No JOIN steps. No plaintext names."""
    schema = "\n".join(f"  {name} = {k[name]}" for name in KEYS)
    return "\n".join(
        [
            "PROTOCOL (English; this is the only readable instruction):",
            "- QUESTION is encoded. Do not try to read English from those tokens.",
            "- CONTEXT keys and values are encoded the same way.",
            "- Isomorphism: identical tokens are the same entity or the same field.",
            "  Matching tokens is equality, not decryption.",
            "- KEY_SCHEMA below is bilingual: English meaning = sealed key token.",
            "- How to use: one QUESTION token is also an employee id in CONTEXT; that is START.",
            "  The encoded question asks for that person's country (not city).",
            "  Use the schema names (employees, id, employer, orgs, hq, country) and token",
            "  equality to walk CONTEXT. Return one sealed atom. No JOIN/PATH is given.",
            "",
            "KEY_SCHEMA (English name → sealed JSON key):",
            schema,
        ]
    )


def rel_legend(sealer: EntitySeal, rels: list[str]) -> str:
    lines = ["REL_SCHEMA (English relation → sealed token):"]
    for r in rels:
        lines.append(f"{r} = {sealer.atom(r)}")
    lines.append("Use the schema to walk CONTEXT. No PATH is given. Return the final sealed tail.")
    return "\n".join(lines)


def build_small(n: int = N) -> dict:
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED_SMALL)
    recs = rng.sample(graph.records, n)
    pool = [r for r in graph.records if r not in recs]
    small, out = _small_paths(n)
    if small.exists():
        for p in small.rglob("prompt.txt"):
            p.unlink()

    cases = []
    arms: dict[str, dict] = {
        "JOIN": {"ids": [], "item_paths": [], "sealed_answer": True},
        "LEGEND": {"ids": [], "item_paths": [], "sealed_answer": True},
        "META": {"ids": [], "item_paths": [], "sealed_answer": True},
        "NOLEG": {"ids": [], "item_paths": [], "sealed_answer": True},
    }

    for i, row in enumerate(recs):
        person, company, hq = row["person"], row["company"], row["hq"]
        country = country_of(hq)
        display = person.replace("_", " ")
        app_q = f"What is the country of {display}?"
        others = rng.sample(pool, 2)
        sealer = EntitySeal(rng.randbytes(16))
        k = {name: sealer.atom(f"JSONKEY:{name}") for name in KEYS}
        pS, cS, hS, nS = (sealer.atom(x) for x in (person, company, hq, country))
        q_country = sealer.atom("country")

        employees = [{k["id"]: pS, k["employer"]: cS}]
        orgs = [{k["id"]: cS, k["hq"]: nest(k["city"], k["country"], hS, nS, rng)}]
        for d in others:
            dc = country_of(d["hq"])
            employees.append(
                {k["id"]: sealer.atom(d["person"]), k["employer"]: sealer.atom(d["company"])}
            )
            orgs.append(
                {
                    k["id"]: sealer.atom(d["company"]),
                    k["hq"]: nest(
                        k["city"],
                        k["country"],
                        sealer.atom(d["hq"]),
                        sealer.atom(dc),
                        rng,
                    ),
                }
            )
        rng.shuffle(employees)
        rng.shuffle(orgs)
        ctx = json.dumps({k["employees"]: employees, k["orgs"]: orgs}, indent=2)
        layer_q = seal_question(f"What is the country of {pS}?", sealer, {pS})
        assert walk_json(employees, orgs, k, pS) == nS
        assert q_country != k["country"], "question word must not equal JSON key"

        join = (
            "JOIN_QUERY\n"
            f"START {pS}\n"
            f"In array {k['employees']}, match {k['id']} = START, take {k['employer']}.\n"
            f"In array {k['orgs']}, match {k['id']} = that employer, take {k['hq']}.{k['country']}.\n"
            "Return that atom."
        )
        legend = legend_block(k)
        meta = meta_block(k)
        names = (
            person,
            display,
            company,
            hq,
            country,
            *[d["person"].replace("_", " ") for d in others],
        )

        for arm, extra, header in (
            (
                "JOIN",
                join + "\n",
                "ARM JOIN: layer bound START, HMAC'd Q, HMAC'd JSON keys+values, attached JOIN.",
            ),
            (
                "LEGEND",
                legend + "\n",
                "ARM LEGEND: layer bound START, HMAC'd Q, HMAC'd JSON keys+values, English key schema. No JOIN.",
            ),
            (
                "META",
                meta + "\n",
                "ARM META: sealed Q+values; bilingual schema; English protocol (encoding + isomorphism + how to use). No JOIN.",
            ),
            (
                "NOLEG",
                "",
                "ARM NOLEG: layer bound START, HMAC'd Q, HMAC'd JSON keys+values. No schema. No JOIN.",
            ),
        ):
            cid = f"SLL_SMALL_{arm}_{i}"
            body = pack(cid, header, layer_q, extra, ctx)
            leaked = leak_check(body, *names)
            path = small / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            rec = {
                "family": "small",
                "arm": arm,
                "i": i,
                "id": cid,
                "gold": nS,
                "trap": hS,
                "start": pS,
                "start_in_q": pS in layer_q,
                "english_in_q": bool(ENGLISH_Q.search(layer_q)),
                "plaintext_in_prompt": leaked,
                "q_country_eq_key": q_country == k["country"],
                "path": repo_rel(path),
                "iso": True,
                "per_item_key": True,
                "app_q": app_q,
                "plain_country": country,
                "engine_ok": True,
            }
            cases.append(rec)
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

    h = {
        "n": n,
        "suite": "seal_layer_legend",
        "family": "small",
        "seed": SEED_SMALL,
        "protocol": "isolation; per-item HMAC; start bound in Q; keys namespaced JSONKEY:",
        "nonclaim": (
            "LEGEND is schema-only. META adds English protocol (encoded Q/values, "
            "token equality, how to use schema) but no JOIN steps. "
            "Not confidentiality. City token is the trap. "
            "JSONKEY: namespace so HMAC(country) in Q ≠ country JSON key."
        ),
        "arms": arms,
        "cases": cases,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False))
    leaks = sum(c["plaintext_in_prompt"] for c in cases)
    print(
        json.dumps(
            {
                "n": n,
                "leaks": leaks,
                "q_country_eq_key": sum(c["q_country_eq_key"] for c in cases),
                "out": str(out),
            },
            indent=2,
        )
    )
    return h


def build_complex(n: int = N) -> dict:
    graph = json.loads((ROOT / "data/real/wikidata_ceo_hops_v2.json").read_text())
    rng = random.Random(SEED_COMPLEX)
    recs = graph[:]
    rng.shuffle(recs)
    makers = [world_hr, world_ticket, world_oncall]
    cx = RUNS / "complex"
    if cx.exists():
        for p in cx.rglob("prompt.txt"):
            p.unlink()

    cases = []
    arms: dict[str, dict] = {
        "PATH": {"ids": [], "item_paths": [], "sealed_answer": True},
        "LEGEND": {"ids": [], "item_paths": [], "sealed_answer": True},
        "NOLEG": {"ids": [], "item_paths": [], "sealed_answer": True},
    }

    for i in range(n):
        w = makers[i % 3](rng, recs, i * 5)
        sealer = EntitySeal(rng.randbytes(16))
        start_s = sealer.atom(w["start"])
        gold = sealer.atom(w["end"])
        rels_s = [sealer.atom(r) for r in w["rels"]]
        sealed_edges = [sealer.triple(*e) for e in w["edges"]]
        outs = SealRouter(sealed_edges).path(start_s, rels_s)
        assert list(dict.fromkeys(outs)) == [gold], (w["use"], outs)
        trap = sealer.atom(recs[i * 5 + 1]["hq"])
        if trap == gold:
            trap = sealer.atom("TRAP")
        bound, _injected = bind_span(w["q3"], w["start"], start_s)
        bound_q = seal_question(bound, sealer, {start_s})
        ctx = render_complex(w, sealer=sealer)
        prog = path_program(start_s, rels_s).body
        legend = rel_legend(sealer, w["rels"])
        people = [p["person"] for p in recs[i * 5 : i * 5 + 5]]
        names = (
            w["start"],
            w["start"].replace("_", " "),
            w["end"],
            *[p.replace("_", " ") for p in people],
            *people,
        )

        for arm, extra, header in (
            (
                "PATH",
                prog + "\n",
                f"ARM PATH family=COMPLEX use={w['use']}: bound START, HMAC Q, PATH given.",
            ),
            (
                "LEGEND",
                legend + "\n",
                f"ARM LEGEND family=COMPLEX use={w['use']}: bound START, HMAC Q, relation schema. No PATH.",
            ),
            (
                "NOLEG",
                "",
                f"ARM NOLEG family=COMPLEX use={w['use']}: bound START, HMAC Q. No schema. No PATH.",
            ),
        ):
            cid = f"SLL_CX_{arm}_{i}"
            body = pack(cid, header, bound_q, extra, ctx)
            path = cx / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            rec = {
                "family": "complex",
                "arm": arm,
                "i": i,
                "id": cid,
                "use": w["use"],
                "gold": gold,
                "trap": trap,
                "start": start_s,
                "start_in_q": start_s in bound_q,
                "english_in_q": bool(ENGLISH_Q.search(bound_q)),
                "plaintext_in_prompt": leak_check(body, *names),
                "path": repo_rel(path),
                "iso": True,
                "per_item_key": True,
                "app_q": w["q3"],
                "unique_3hop": True,
            }
            cases.append(rec)
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

    h = {
        "n": n,
        "suite": "seal_layer_legend",
        "family": "complex",
        "seed": SEED_COMPLEX,
        "nonclaim": (
            "COMPLEX worlds are unique 3-hop from START, so NOLEG may still walk. "
            "That is not the city-vs-country schema test. Not confidentiality."
        ),
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "seal_layer_legend_complex_harness.json"
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False))
    print(json.dumps({"n": n, "leaks": sum(c["plaintext_in_prompt"] for c in cases), "out": str(out)}, indent=2))
    return h


def score(harness_name: str, model: str) -> None:
    H = json.loads((RESULTS / harness_name).read_text())
    stem = Path(harness_name).stem
    preds = {}
    d = RESULTS / f"{stem}_replies_{model}"
    if d.exists():
        for p in d.rglob("*.txt"):
            text = p.read_text()
            tagged = list(SEAL.finditer(text))
            for m in tagged:
                preds[m.group(1)] = m.group(2).strip()
            if not tagged:
                mm = re.search(r"SLL_(?:SMALL|CX)_[A-Z]+_\d+", text)
                if mm and re.search(r"\bUNKNOWN\b", text, re.I):
                    preds[mm.group(0)] = "UNKNOWN"
    rows = []
    for c in H["cases"]:
        pred = preds.get(c["id"], "MISSING")
        if pred == c["gold"]:
            kind = "gold"
        elif pred.upper() == "UNKNOWN":
            kind = "unknown"
        elif pred == c.get("trap"):
            kind = "trap"
        elif pred == "MISSING":
            kind = "missing"
        else:
            kind = "other"
        rows.append({**{k: v for k, v in c.items() if k != "path"}, "pred": pred, "kind": kind, "ok": kind == "gold"})

    def arm_sum(arm: str):
        rs = [r for r in rows if r["arm"] == arm]
        n = len(rs)
        gold = sum(1 for r in rs if r["kind"] == "gold")
        missing = sum(1 for r in rs if r["kind"] == "missing")
        return {
            "score": locked_score(gold, n, missing=missing),
            "wilson": wilson(gold, n) if n and missing < n else None,
            "gold": gold,
            "unknown": sum(1 for r in rs if r["kind"] == "unknown"),
            "trap": sum(1 for r in rs if r["kind"] == "trap"),
            "missing": missing,
            "other": sum(1 for r in rs if r["kind"] == "other"),
        }

    summary = {arm: arm_sum(arm) for arm in H["arms"]}
    path = RESULTS / f"{stem}_{model}.json"
    path.write_text(
        json.dumps(
            {"model": model, "n": H["n"], "summary": summary, "nonclaim": H["nonclaim"], "rows": rows},
            indent=2,
        )
    )
    print(json.dumps(summary, indent=2))
    print("wrote", path)


def prove_small() -> None:
    """Non-LLM: JOIN and legend maps are executable; Q-word ≠ JSON key."""
    h = json.loads((RESULTS / "seal_layer_legend_small_harness.json").read_text())
    assert all(not c["plaintext_in_prompt"] for c in h["cases"])
    assert all(not c["q_country_eq_key"] for c in h["cases"])
    print(json.dumps({"prove_small": "ok", "n": h["n"], "leaks": 0, "q_eq_key": 0}))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "small"
    if cmd == "small":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else N
        build_small(n)
        if n == N:
            prove_small()
    elif cmd == "complex":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else N
        build_complex(n)
    elif cmd == "score":
        score(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "gpt56")
    else:
        raise SystemExit("usage: seal_layer_legend.py [small [n]|complex [n]|score harness.json tag]")
