#!/usr/bin/env python3
"""
SEAL-Bench-Real — camera-ready query-form factorial.

Same Wikidata CEO→company→HQ graphs; only QUERY FORM changes.
Produces isolated *_ONLY batches + harness for paper Table 1.

Forms:
  NL        — sealed natural-language question
  SCAFFOLD  — sealed NL + forced MID then ANSWER
  STRUCT    — language-free structural rule (unique pure-sink 2-hop)
  DEMO      — 2 sealed demos then quiz (same encoding)
  PROG      — sealed PATH_QUERY (compiler output)
  ROUTER    — symbolic SealRouter upper bound (no LLM)

Integrity: twins for PROG; edge-order shuffled; isolated dirs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from nl_to_path_compiler import DEFAULT_TEMPLATES, PathCompiler  # noqa: E402
from seal_router import SealRouter  # noqa: E402

DATA = json.loads((ROOT / "data/real/wikidata_ceo_hops_v2.json").read_text())
RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "factorial"
KEY = b"oir-seal-bench-real-factorial-v1"
SEED = 20260727
N_QUIZ = 24
N_DEMO = 2


class EntitySeal:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def atom(self, a: str) -> str:
        if a not in self.fwd:
            d = hmac.new(self.key, a.encode(), hashlib.sha256).digest()
            t = "E" + d[:6].hex()
            self.fwd[a] = t
            self.rev[t] = a
        return self.fwd[a]

    def text(self, s: str) -> str:
        return "".join(
            self.atom(p) if re.fullmatch(r"[A-Za-z0-9_]+", p) else p
            for p in re.findall(r"[A-Za-z0-9_]+|[^A-Za-z0-9_]+", s)
        )


def build_edges(person, company, hq, decoy, *, twin=False, shuffle_rng: random.Random):
    """Ambiguous multi-sink graph. twin=True rewires person→decoy employer."""
    if twin:
        co, city = decoy["company"], decoy["hq"]
        dist_co, dist_hq = company, hq
    else:
        co, city = company, hq
        dist_co, dist_hq = decoy["company"], decoy["hq"]
    hold, part = f"Hold_{co}", f"Part_{co}"
    edges = [
        (person, "works_at", co),
        (co, "headquartered_in", city),
        (dist_co, "headquartered_in", dist_hq),
        (co, "owned_by", hold),
        (hold, "meta_of", f"Meta_{co}"),
        (co, "partner_of", part),
        (part, "meta_of", f"PMeta_{co}"),
        (f"DecoyPerson_{dist_co}", "works_at", dist_co),
    ]
    seen, out = set(), []
    for e in edges:
        if e not in seen:
            seen.add(e)
            out.append(e)
    shuffle_rng.shuffle(out)
    return out


def render(sealer: EntitySeal, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def write_batch(name: str, header: str, items: list[tuple[str, str]]):
    d = RUNS / f"{name}_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "Same encoding on question and context. No external world knowledge.\n",
        "Format unless overridden: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        header + "\n",
    ]
    for cid, body in items:
        lines.append(f"\n##### ID {cid} #####\n{body}\n")
    (d / "BATCH.txt").write_text("\n".join(lines))
    return str(d / "BATCH.txt")


def main():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    for r in ("works_at", "headquartered_in", "owned_by", "partner_of", "meta_of"):
        sealer.atom(r)

    pool = []
    seen = set()
    for r in DATA:
        if r["person"] in seen or re.match(r"^Q\d+$", r["person"]):
            continue
        seen.add(r["person"])
        pool.append(r)
    rng.shuffle(pool)
    assert len(pool) >= N_QUIZ + N_DEMO + 5, len(pool)

    demos = pool[:N_DEMO]
    quiz = pool[N_DEMO : N_DEMO + N_QUIZ]
    lexicon = {r["person"] for r in pool}
    compiler = PathCompiler(lexicon)

    cases = []
    buckets: dict[str, list[tuple[str, str]]] = {
        "NL": [],
        "SCAFFOLD": [],
        "STRUCT": [],
        "DEMO": [],
        "PROG": [],
        "PROG_TWIN": [],
    }

    # Prebuild demo block (sealed) for DEMO condition
    demo_blocks = []
    for j, drow in enumerate(demos):
        decoy = rng.choice([r for r in pool if r["company"] != drow["company"]])
        edges = build_edges(drow["person"], drow["company"], drow["hq"], decoy, twin=False, shuffle_rng=random.Random(SEED + 100 + j))
        prog = compiler.seal_program(drow["person"], sealer.atom)
        ans = sealer.atom(drow["hq"])
        demo_blocks.append(
            f"DEMO {j}:\n{prog}\nCONTEXT:\n{render(sealer, edges)}\nANSWER_SEALED: {ans}"
        )
    demo_preamble = "\n\n".join(demo_blocks) + "\n\nNow answer the QUIZ items the same way.\n"

    for i, row in enumerate(quiz):
        decoy = rng.choice([r for r in pool if r["company"] != row["company"]])
        person, company, hq = row["person"], row["company"], row["hq"]
        tmpl = DEFAULT_TEMPLATES[i % len(DEFAULT_TEMPLATES)]
        nl = tmpl.format(person=person if i % 2 == 0 else person.replace("_", " "))
        assert compiler.compile(nl).ok

        edge_rng = random.Random(SEED + 1000 + i)
        edges = build_edges(person, company, hq, decoy, twin=False, shuffle_rng=edge_rng)
        ctx = render(sealer, edges)
        exp = sealer.atom(hq)
        mid = sealer.atom(company)
        prog = compiler.seal_program(person, sealer.atom)
        q_sealed = sealer.text(nl)

        # ROUTER bound
        triples = [(sealer.atom(h), sealer.atom(r), sealer.atom(t)) for h, r, t in edges]
        router_out = SealRouter(triples).path(
            sealer.atom(person), [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        )
        assert list(dict.fromkeys(router_out)) == [exp], (i, router_out, exp)

        base = {
            "i": i,
            "person": person,
            "company": company,
            "hq": hq,
            "expect": exp,
            "intermediate_company": mid,
            "nl": nl,
            "decoy_company": decoy["company"],
            "decoy_hq": decoy["hq"],
        }

        cid = f"FAC_NL_{i}"
        buckets["NL"].append((cid, f"QUESTION:\n{q_sealed}\n\nCONTEXT:\n{ctx}"))
        cases.append({**base, "id": cid, "form": "NL"})

        cid = f"FAC_SCAFFOLD_{i}"
        buckets["SCAFFOLD"].append(
            (
                cid,
                f"QUESTION:\n{q_sealed}\n\nCONTEXT:\n{ctx}\n\n"
                f"Reply exactly:\nMID_SEALED[{cid}]: <seal>\nANSWER_SEALED[{cid}]: <seal>\n"
                f"(MID = first hop tail; ANSWER = final location)",
            )
        )
        cases.append({**base, "id": cid, "form": "SCAFFOLD", "expect_mid": mid})

        cid = f"FAC_STRUCT_{i}"
        buckets["STRUCT"].append(
            (
                cid,
                "RULE: Find the unique length-2 path from the START entity that ends at a "
                "pure sink (node with out-degree 0). Return that sink seal only.\n"
                f"START: {sealer.atom(person)}\n\nCONTEXT:\n{ctx}",
            )
        )
        cases.append({**base, "id": cid, "form": "STRUCT"})

        cid = f"FAC_DEMO_{i}"
        buckets["DEMO"].append((cid, f"{demo_preamble}\nQUIZ {cid}:\n{prog}\n\nCONTEXT:\n{ctx}"))
        cases.append({**base, "id": cid, "form": "DEMO"})

        cid = f"FAC_PROG_{i}"
        buckets["PROG"].append((cid, f"{prog}\n\nCONTEXT:\n{ctx}"))
        cases.append({**base, "id": cid, "form": "PROG"})

        # twin
        twin_rng = random.Random(SEED + 2000 + i)
        edges_t = build_edges(person, company, hq, decoy, twin=True, shuffle_rng=twin_rng)
        ctx_t = render(sealer, edges_t)
        exp_t = sealer.atom(decoy["hq"])
        triples_t = [(sealer.atom(h), sealer.atom(r), sealer.atom(t)) for h, r, t in edges_t]
        rout_t = SealRouter(triples_t).path(
            sealer.atom(person), [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        )
        assert list(dict.fromkeys(rout_t)) == [exp_t]
        cid = f"FAC_TWIN_{i}"
        buckets["PROG_TWIN"].append((cid, f"{prog}\n\nCONTEXT:\n{ctx_t}"))
        cases.append(
            {
                **base,
                "id": cid,
                "form": "PROG_TWIN",
                "expect": exp_t,
                "original_expect": exp,
                "plain_hq": decoy["hq"],
            }
        )

    headers = {
        "NL": "FORM NL: sealed natural-language question.",
        "SCAFFOLD": "FORM SCAFFOLD: sealed NL; report MID then ANSWER.",
        "STRUCT": "FORM STRUCT: language-free pure-sink 2-hop rule.",
        "DEMO": "FORM DEMO: sealed demos then quiz path-program.",
        "PROG": "FORM PROG: sealed PATH_QUERY only.",
        "PROG_TWIN": "FORM PROG_TWIN: same program, counterfactual employer wiring.",
    }
    paths = {k: write_batch(k, headers[k], v) for k, v in buckets.items()}

    harness = {
        "bench": "SEAL-Bench-Real query-form factorial",
        "n_quiz": N_QUIZ,
        "n_demo": N_DEMO,
        "seed": SEED,
        "paper_table": "query form × HQ accuracy / company-stop / twin flip",
        "forms": list(buckets.keys()),
        "paths": paths,
        "rev": sealer.rev,
        "cases": cases,
        "router_bound": {"PROG": f"{N_QUIZ}/{N_QUIZ}", "PROG_TWIN": f"{N_QUIZ}/{N_QUIZ}"},
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "seal_bench_real_factorial_harness.json").write_text(json.dumps(harness, indent=2))
    print(
        json.dumps(
            {
                "n_cases": len(cases),
                "n_quiz": N_QUIZ,
                "forms": {k: len(v) for k, v in buckets.items()},
                "router_bound": harness["router_bound"],
                "out": str(RESULTS / "seal_bench_real_factorial_harness.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
