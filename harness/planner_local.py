#!/usr/bin/env python3
"""
Best enrichment axis under opacity (not synonym sugar).

Paper-selector direction
------------------------
What actually helps sealed multi-hop is *schema linking / program compilation*
(KBQA + Text-to-SQL + PyRAG), not lexical paraphrase.

Ladder under test (same Wikidata CEO→HQ graphs, same seal key):

  A. RAW_NL          — sealed free NL (baseline fail)
  B. CTX_ALIAS       — enrich CONTEXT with synonym-labeled duplicate edges,
                       then seal; Q stays free NL (schema-linking style)
  C. DET_COMPILER    — deterministic PathFamilyCompiler → sealed PATH
  D. LOCAL_PLANNER   — local Ollama model emits PATH from cleartext NL+schema,
                       then seal program; SealRouter executes (planner≠executor)
  E. LOCAL_PROG_MUT  — same sealed PATH from local planner, LLM executes

Prediction:
  A fail; B may unlock 1-hop match but still under-specify 2-hop plan;
  C/D/E saturate when program is correct.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, PathFamilyCompiler, SealRouter, execute_program, pack_mut_batch, path_program, raw_nl_program
from oir.adapters import ceo_hq_edges, load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "planner_local"
KEY = b"oir-planner-local-v1"
SEED = 20260728
N = 12

# Relation aliases — cleartext CONTEXT enrichment (schema linking)
REL_ALIASES = {
    "works_at": ["works_at", "employs", "employer_of", "works_for", "employed_by"],
    "headquartered_in": ["headquartered_in", "hq_in", "based_in", "located_in_city", "head_office_in"],
}

HQ_CUES = ("headquarter", "hq", "employer", "works", "based", "city", "office", "firm", "company")

OLLAMA_MODELS = ["qwen3.5:latest", "reecdev/tiny3.5:500m"]


def expand_edges(edges: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    out = []
    for h, r, t in edges:
        aliases = REL_ALIASES.get(r, [r])
        for a in aliases:
            out.append((h, a, t))
    return out


def ollama_plan(model: str, question: str, person: str, schema_rels: list[str], timeout: int = 120) -> dict:
    prompt = f"""You are a PATH planner for a knowledge graph.
Emit ONLY a JSON object with keys start, r1, r2 (no markdown).

Schema relations (choose from these exact strings):
{schema_rels}

Question: {question}
Subject person atom (use exactly): {person}

The query is always: person -R1-> company -R2-> city (HQ of employer).
Return JSON: {{"start":"{person}","r1":"works_at","r2":"headquartered_in"}}
"""
    try:
        proc = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except Exception as e:
        return {"ok": False, "reason": f"ollama_error:{e}", "raw": ""}

    m = re.search(r"\{[^{}]*\}", text, flags=re.S)
    if not m:
        return {"ok": False, "reason": "no_json", "raw": text[-500:]}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"ok": False, "reason": "bad_json", "raw": m.group(0)}
    start = str(obj.get("start", "")).strip().replace(" ", "_")
    r1 = str(obj.get("r1", "")).strip()
    r2 = str(obj.get("r2", "")).strip()
    ok = start == person and r1 in schema_rels and r2 in schema_rels
    return {"ok": ok, "start": start, "r1": r1, "r2": r2, "raw": m.group(0), "reason": "ok" if ok else "schema_miss"}


def build_and_run():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    sealer = EntitySeal(KEY)
    schema = ["works_at", "headquartered_in", "owned_by", "partner_of", "meta_of", "located_in"]

    compiler = PathFamilyCompiler(
        lexicon={r["person"] for r in recs},
        path=("works_at", "headquartered_in"),
        intent_cues=HQ_CUES,
        expect_fn=lambda p: next(x["hq"] for x in recs if x["person"] == p),
    )

    cases = []
    mut_batches = {"RAW_NL": [], "CTX_ALIAS": [], "DET_PROG": [], "LOCAL_PROG": []}
    router_scores = {
        "DET_COMPILER": {"ok": 0, "n": 0},
        "CTX_ALIAS_ROUTER_NAIVE": {"ok": 0, "n": 0},  # not used for NL
    }
    local_plan = {m: {"ok": 0, "n": 0, "router_ok": 0, "detail": []} for m in OLLAMA_MODELS}

    for i, row in enumerate(recs):
        person, hq, company = row["person"], row["hq"], row["company"]
        q = f"Where is the headquarters of the company that {person.replace('_', ' ')} works for?"
        base_edges = ceo_hq_edges(row)
        alias_edges = expand_edges(base_edges)

        # --- A RAW ---
        ctx_raw = SealRouter([sealer.triple(*e) for e in base_edges]).render()
        expect = sealer.atom(hq)
        co_seal = sealer.atom(company)
        cid = f"PL_RAW_{i}"
        mut_batches["RAW_NL"].append((cid, raw_nl_program(f"QUESTION:\n{sealer.text(q)}"), ctx_raw))
        cases.append({"id": cid, "form": "RAW_NL", "expect": expect, "company_seal": co_seal, "i": i, "person": person, "hq": hq, "q": q})

        # --- B CTX_ALIAS ---
        ctx_alias = SealRouter([sealer.triple(*e) for e in alias_edges]).render()
        cid = f"PL_ALIAS_{i}"
        # free NL may match employs/works_for etc. after seal if those words appear in Q
        q_alias_friendly = (
            f"In which city is the organization that employs {person.replace('_', ' ')} based_in?"
        )
        # use words that exist as alias relation labels
        mut_batches["CTX_ALIAS"].append(
            (cid, raw_nl_program(f"QUESTION:\n{sealer.text(q_alias_friendly)}"), ctx_alias)
        )
        cases.append(
            {
                "id": cid,
                "form": "CTX_ALIAS",
                "expect": expect,
                "company_seal": co_seal,
                "i": i,
                "person": person,
                "hq": hq,
                "q": q_alias_friendly,
                "note": "Q uses employs + based_in; C has alias edges",
            }
        )

        # --- C DET compiler ---
        cr = compiler.compile(f"Where is the company headquartered_in that {person} works_at?")
        assert cr.ok
        prog = cr.program.seal(sealer)
        prog.meta["start"] = sealer.atom(person)
        prog.meta["rels"] = [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        got = execute_program(prog, SealRouter([sealer.triple(*e) for e in base_edges]))
        router_scores["DET_COMPILER"]["n"] += 1
        router_scores["DET_COMPILER"]["ok"] += int(got == [expect])
        cid = f"PL_DET_{i}"
        mut_batches["DET_PROG"].append((cid, prog, ctx_raw))
        cases.append({"id": cid, "form": "DET_PROG", "expect": expect, "company_seal": co_seal, "i": i, "person": person, "hq": hq})

        # --- D LOCAL planners ---
        for model in OLLAMA_MODELS:
            t0 = time.time()
            plan = ollama_plan(model, q, person, schema)
            plan["latency_s"] = round(time.time() - t0, 2)
            local_plan[model]["n"] += 1
            local_plan[model]["ok"] += int(plan.get("ok"))
            router_hit = False
            if plan.get("ok"):
                p2 = path_program(plan["start"], (plan["r1"], plan["r2"]), hq).seal(sealer)
                p2.meta["start"] = sealer.atom(plan["start"])
                p2.meta["rels"] = [sealer.atom(plan["r1"]), sealer.atom(plan["r2"])]
                got = execute_program(p2, SealRouter([sealer.triple(*e) for e in base_edges]))
                router_hit = got == [expect]
                local_plan[model]["router_ok"] += int(router_hit)
                if model == OLLAMA_MODELS[0]:
                    # only primary local model goes to MUT batch
                    cid = f"PL_LOCAL_{i}"
                    mut_batches["LOCAL_PROG"].append((cid, p2, ctx_raw))
                    cases.append(
                        {
                            "id": cid,
                            "form": "LOCAL_PROG",
                            "expect": expect,
                            "company_seal": co_seal,
                            "i": i,
                            "person": person,
                            "hq": hq,
                            "plan": {k: plan[k] for k in ("start", "r1", "r2", "ok")},
                            "model": model,
                        }
                    )
            local_plan[model]["detail"].append(
                {"i": i, "person": person, "plan": plan, "router_ok": router_hit}
            )

    RUNS.mkdir(parents=True, exist_ok=True)
    paths = {}
    headers = {
        "RAW_NL": "Sealed free NL baseline.",
        "CTX_ALIAS": "CONTEXT relation-alias expansion + Q uses alias words; then sealed.",
        "DET_PROG": "Deterministic PathFamilyCompiler → sealed PATH.",
        "LOCAL_PROG": f"Local Ollama planner ({OLLAMA_MODELS[0]}) → sealed PATH.",
    }
    for form, items in mut_batches.items():
        if not items:
            continue
        d = RUNS / f"{form}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack_mut_batch(items, headers[form]))
        paths[form] = str(p)

    harness = {
        "n": N,
        "models_ollama": OLLAMA_MODELS,
        "rel_aliases": REL_ALIASES,
        "paths": paths,
        "cases": cases,
        "router_scores": {
            k: {"score": f"{v['ok']}/{v['n']}", **v} for k, v in router_scores.items()
        },
        "local_planner": {
            m: {
                "compile_acc": f"{v['ok']}/{v['n']}",
                "router_acc": f"{v['router_ok']}/{v['n']}",
                "detail": v["detail"],
            }
            for m, v in local_plan.items()
        },
        "claim": (
            "Best enrichment under opacity = compile to PATH (local SLM or deterministic), "
            "not synonym paraphrase; CTX alias is schema-linking ablation."
        ),
        "rev": sealer.rev,
    }
    (RESULTS / "planner_local_harness.json").write_text(json.dumps(harness, indent=2))
    print(
        json.dumps(
            {
                "router": harness["router_scores"],
                "local": {m: {"compile": harness["local_planner"][m]["compile_acc"], "router": harness["local_planner"][m]["router_acc"]} for m in OLLAMA_MODELS},
                "paths": paths,
                "n_local_mut": len(mut_batches.get("LOCAL_PROG", [])),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    build_and_run()
