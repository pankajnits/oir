#!/usr/bin/env python3
"""2Wiki-CF: counterfactual hop-2 tails + competing path + span-aligned start.

Falsifier: PLAIN_NL that emits the original 2Wiki/Wikipedia answer used the lexicon,
not the graph. Gold is a nonce CF tail in the prompt-local graph.

Also: MODEL_PLAN — write PATH from English Q + graph, no gold program (G-Inc2).
G-Rev1 remains unclaimed.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter, path_program

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "wiki_cf"
KEY = b"oir-wiki-cf-v1"
SEED = 20260813
N = 12
SRC = ROOT / "data" / "2wiki_compositional_n12.json"


def replace_spans(text: str, sealer: EntitySeal, atoms: list[str]) -> str:
    out = text
    for a in sorted({x for x in atoms if x}, key=len, reverse=True):
        variants = {a, a.replace("_", " ")}
        for v in sorted(variants, key=len, reverse=True):
            if len(v) < 3:
                continue
            out = re.sub(re.escape(v), sealer.atom(a), out, flags=re.I)
    return out


def pack(kind: str, header: str, items: list[tuple[str, str, str]]) -> str:
    tag = "ANSWER_PLAIN" if kind == "plain" else "ANSWER_SEALED"
    hint = "<answer_or_UNKNOWN>" if kind == "plain" else "<seal_or_UNKNOWN>"
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No decrypt. No world knowledge.",
        f"Format: {tag}[<id>]: {hint}",
        "Answer EVERY ID. If ambiguous, UNKNOWN.",
        "",
        header,
        "",
    ]
    for cid, body, ctx in items:
        lines.append(f"##### ID {cid} #####\n{body}\n\nCONTEXT:\n{ctx}\n")
    return "\n".join(lines)


def build():
    items = json.loads(SRC.read_text())["items"][:N]
    sealer = EntitySeal(KEY)
    rng = random.Random(SEED)
    cases = []
    buckets = {k: [] for k in ("PLAIN_NL", "SPAN_NL", "SEAL_PROG", "MODEL_PLAN")}

    # per-item graphs (not a shared 24-triple union) + competing trap to original wiki answer
    for i, it in enumerate(items):
        ev = it["evidences"]
        start, r1, mid = ev[0]
        _, r2, wiki = ev[1]
        cf = f"CF_TAIL_{i}_{re.sub(r'[^A-Za-z0-9]+', '', wiki)[:12] or 'X'}"
        trap_rel = f"decoy_link_{i}"
        trap_mid = f"decoy_mid_{i}"
        edges = [
            (start, r1, mid),
            (mid, r2, cf),  # gold
            (start, trap_rel, trap_mid),
            (trap_mid, r2, wiki),  # Wikipedia original = trap
        ]
        # two distractor chains from other items (original, not CF)
        for j in ((i + 1) % N, (i + 2) % N):
            e0, e1 = items[j]["evidences"]
            edges += [tuple(e0), tuple(e1)]
        rng.shuffle(edges)
        plain_ctx = SealRouter(edges).render()
        sealed = [sealer.triple(*e) for e in edges]
        sealed_ctx = SealRouter(sealed).render()
        gold_seal = sealer.atom(cf)
        wiki_seal = sealer.atom(wiki)
        outs = SealRouter(sealed).path(sealer.atom(start), [sealer.atom(r1), sealer.atom(r2)])
        assert list(dict.fromkeys(outs)) == [gold_seal], (outs, cf)

        q = it["question"]
        q_span = replace_spans(q, sealer, [start, mid, wiki, cf])
        start_in = sealer.atom(start) in q_span
        prog = path_program(start, (r1, r2), cf)
        prog_s = prog.seal(sealer)
        prog_s.meta["start"] = sealer.atom(start)
        prog_s.meta["rels"] = [sealer.atom(r1), sealer.atom(r2)]

        ids = {
            "PLAIN_NL": f"CF_PLAINNL_{i}",
            "SPAN_NL": f"CF_SPANNL_{i}",
            "SEAL_PROG": f"CF_SEALPROG_{i}",
            "MODEL_PLAN": f"CF_MODELPLAN_{i}",
        }
        buckets["PLAIN_NL"].append((ids["PLAIN_NL"], f"QUESTION:\n{q}", plain_ctx))
        buckets["SPAN_NL"].append((ids["SPAN_NL"], f"QUESTION:\n{q_span}", sealed_ctx))
        buckets["SEAL_PROG"].append((ids["SEAL_PROG"], prog_s.body, sealed_ctx))
        buckets["MODEL_PLAN"].append(
            (
                ids["MODEL_PLAN"],
                "Write a PATH_QUERY (START / R1 / R2 using CONTEXT tokens only), then the answer.\n"
                f"QUESTION:\n{q_span}\n"
                "Also emit the final tail as ANSWER_SEALED.",
                sealed_ctx,
            )
        )
        cases.append(
            {
                "i": i,
                "wiki_id": it["id"],
                "question": q,
                "wiki_answer": wiki,
                "cf_gold": cf,
                "expect_plain": cf,
                "expect_seal": gold_seal,
                "wiki_seal": wiki_seal,
                "start": start,
                "rels": [r1, r2],
                "start_seal_in_span_q": start_in,
                "ids": ids,
            }
        )

    RUNS.mkdir(parents=True, exist_ok=True)
    headers = {
        "PLAIN_NL": "ARM PLAIN_NL: English question + plaintext KG. Gold is the CF tail IN CONTEXT, not Wikipedia.",
        "SPAN_NL": "ARM SPAN_NL: entity-span seals (start should be in Q) + sealed KG. No PATH. Competing hop present.",
        "SEAL_PROG": "ARM SEAL_PROG: gold PATH over seals (ceiling).",
        "MODEL_PLAN": "ARM MODEL_PLAN (G-Inc2): write PATH from the question + CONTEXT, then answer. No gold PATH given.",
    }
    kinds = {"PLAIN_NL": "plain", "SPAN_NL": "sealed", "SEAL_PROG": "sealed", "MODEL_PLAN": "sealed"}
    paths = {}
    for arm, items_b in buckets.items():
        d = RUNS / f"{arm}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack(kinds[arm], headers[arm], items_b))
        paths[arm] = str(p)

    n_start = sum(1 for c in cases if c["start_seal_in_span_q"])
    harness = {
        "n": N,
        "suite": "wiki_cf",
        "paths": paths,
        "cases": cases,
        "start_seal_in_span_q": f"{n_start}/{N}",
        "sealrouter_ceiling": f"{N}/{N}",
        "falsifier": "PLAIN_NL == original 2Wiki answer → parametric cheat; gold is CF_TAIL_*",
        "nonclaim": "Not G-Rev1. Competing hop + CF gold. Unigram relation leak in SPAN_NL still possible.",
    }
    out = RESULTS / "wiki_cf_harness.json"
    out.write_text(json.dumps(harness, indent=2, ensure_ascii=False))
    print(json.dumps({"n": N, "start_in_q": f"{n_start}/{N}", "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
