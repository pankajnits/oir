#!/usr/bin/env python3
"""Opaque-relation 2Wiki-CF (kills unigram HMAC leak).

Graph relations are HMAC-sealed. English question keeps "director"/"mother"
which do NOT match graph rel tokens. Competing hop is also opaque.

SPAN_NL should collapse (no copy-and-walk via English rels).
LEGEND restores by mapping English rel → seal.
SEAL_PROG remains the ceiling.
MODEL_PLAN without lexicon is a G-Inc2 pressure test — not G-Rev1.

n=12 from the original pilot items (not the n=200 freeze).
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
RUNS = ROOT / "runs" / "wiki_cf_opaque_rel"
KEY = b"oir-wiki-cf-opaque-rel-v1"
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
    arms = ("PLAIN_NL", "SPAN_NL", "SEAL_PROG", "LEGEND_NL", "MODEL_PLAN")
    buckets = {k: [] for k in arms}

    for i, it in enumerate(items):
        ev = it["evidences"]
        start, r1, mid = ev[0]
        _, r2, wiki = ev[1]
        cf = f"CF_TAIL_{i}_{re.sub(r'[^A-Za-z0-9]+', '', wiki)[:12] or 'X'}"
        trap_rel = f"decoy_link_{i}"
        trap_mid = f"decoy_mid_{i}"
        edges = [
            (start, r1, mid),
            (mid, r2, cf),
            (start, trap_rel, trap_mid),
            (trap_mid, r2, wiki),
        ]
        for j in ((i + 1) % N, (i + 2) % N):
            e0, e1 = items[j]["evidences"]
            edges += [tuple(e0), tuple(e1)]
        rng.shuffle(edges)

        # Seal EVERY atom including relations — English Q rels will not HMAC-match.
        sealed = [sealer.triple(*e) for e in edges]
        sealed_ctx = SealRouter(sealed).render()
        plain_ctx = SealRouter(edges).render()
        gold_seal = sealer.atom(cf)
        wiki_seal = sealer.atom(wiki)
        r1s, r2s = sealer.atom(r1), sealer.atom(r2)
        outs = SealRouter(sealed).path(sealer.atom(start), [r1s, r2s])
        assert list(dict.fromkeys(outs)) == [gold_seal], (outs, cf)

        q = it["question"]
        # entity spans only — leave English relation words readable
        q_span = replace_spans(q, sealer, [start, mid, wiki, cf])
        start_in = sealer.atom(start) in q_span
        rel_leak = sealer.atom(r1) in q_span or sealer.atom(r2) in q_span
        legend = f"LEGEND\n{r1} = {r1s}\n{r2} = {r2s}\n(other CONTEXT rel tokens are distractors)"
        prog = path_program(start, (r1, r2), cf).seal(sealer)

        ids = {
            "PLAIN_NL": f"OR_PLAINNL_{i}",
            "SPAN_NL": f"OR_SPANNL_{i}",
            "SEAL_PROG": f"OR_SEALPROG_{i}",
            "LEGEND_NL": f"OR_LEGEND_{i}",
            "MODEL_PLAN": f"OR_MODELPLAN_{i}",
        }
        buckets["PLAIN_NL"].append((ids["PLAIN_NL"], f"QUESTION:\n{q}", plain_ctx))
        buckets["SPAN_NL"].append(
            (
                ids["SPAN_NL"],
                "English question (entity spans sealed). Graph relations are opaque HMAC tokens.\n"
                f"QUESTION:\n{q_span}",
                sealed_ctx,
            )
        )
        buckets["SEAL_PROG"].append((ids["SEAL_PROG"], prog.body, sealed_ctx))
        buckets["LEGEND_NL"].append(
            (
                ids["LEGEND_NL"],
                f"{legend}\nQUESTION:\n{q_span}",
                sealed_ctx,
            )
        )
        buckets["MODEL_PLAN"].append(
            (
                ids["MODEL_PLAN"],
                "Write a PATH_QUERY using CONTEXT tokens only (no gold PATH). Then the sealed tail.\n"
                f"QUESTION:\n{q_span}",
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
                "rel_seals": [r1s, r2s],
                "start_seal_in_span_q": start_in,
                "rel_seal_in_span_q": rel_leak,
                "ids": ids,
            }
        )

    RUNS.mkdir(parents=True, exist_ok=True)
    headers = {
        "PLAIN_NL": "ARM PLAIN_NL: English Q + plaintext KG. Gold is CF tail IN CONTEXT, not Wikipedia.",
        "SPAN_NL": "ARM SPAN_NL: entity-span seals; RELATIONS in CONTEXT are opaque. No PATH, no legend.",
        "SEAL_PROG": "ARM SEAL_PROG: gold PATH over sealed entities AND relations (ceiling).",
        "LEGEND_NL": "ARM LEGEND_NL: English rel → sealed rel map + span-sealed Q. No PATH.",
        "MODEL_PLAN": "ARM MODEL_PLAN: write PATH from English Q + opaque-rel graph. No gold PATH, no legend.",
    }
    kinds = {a: ("plain" if a == "PLAIN_NL" else "sealed") for a in arms}
    paths = {}
    for arm, items_b in buckets.items():
        d = RUNS / f"{arm}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack(kinds[arm], headers[arm], items_b))
        paths[arm] = str(p)

    n_start = sum(1 for c in cases if c["start_seal_in_span_q"])
    n_leak = sum(1 for c in cases if c["rel_seal_in_span_q"])
    harness = {
        "n": N,
        "suite": "wiki_cf_opaque_rel",
        "paths": paths,
        "cases": cases,
        "start_seal_in_span_q": f"{n_start}/{N}",
        "rel_seal_in_span_q": f"{n_leak}/{N}",
        "sealrouter_ceiling": f"{N}/{N}",
        "hypothesis": "SPAN_NL collapses when relations are opaque; LEGEND/PATH restore. Not G-Rev1.",
        "nonclaim": "Not G-Rev1. MODEL_PLAN without lexicon is expected to fail or leak.",
    }
    out = RESULTS / "wiki_cf_opaque_rel_harness.json"
    out.write_text(json.dumps(harness, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {
                "n": N,
                "start_in_q": f"{n_start}/{N}",
                "rel_leak": f"{n_leak}/{N}",
                "out": str(out),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    build()
