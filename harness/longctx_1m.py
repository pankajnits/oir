#!/usr/bin/env python3
"""
Million-token sealed CONTEXT + binder suite.

Keeps binders (PATH_PROG / COMPLEX / FOLLOW); NL control.
Shared CONTEXT ~1e6 tokens (est.); quizzes are needles in the haystack.
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter, path_program, raw_nl_program
from oir.adapters import ceo_hq_edges, load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "longctx_1m"
KEY = b"oir-longctx-1m-v1"
SEED = 20260728
TARGET_TOKENS = 1_000_000


def est_tokens(s: str) -> int:
    return max(1, len(s) // 4)


def od500_edges(path: Path, limit: int = 529) -> list[tuple[str, str, str]]:
    edges = []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows[:limit]):
        co = re.sub(r"\s+", "_", (r.get("company_name") or f"OD_{i}").strip())[:48] or f"OD_{i}"
        city = re.sub(r"\s+", "_", (r.get("city") or "Unknown").strip())[:48]
        state = re.sub(r"\s+", "_", (r.get("state") or "NA").strip())[:16]
        person = f"ODStaff_{i}"
        edges.extend(
            [
                (person, "works_at", co),
                (co, "headquartered_in", city),
                (co, "in_state", state),
                (co, "owned_by", f"ODHold_{i}"),
                (f"ODHold_{i}", "meta_of", co),
            ]
        )
    return edges


def pad_chunk(start: int, n: int) -> list[tuple[str, str, str]]:
    edges = []
    for i in range(start, start + n):
        p, c, hq = f"PadPerson_{i}", f"PadCo_{i}", f"PadCity_{i}"
        edges.extend(
            [
                (p, "works_at", c),
                (c, "headquartered_in", hq),
                (c, "owned_by", f"PadHold_{i}"),
                (f"PadHold_{i}", "meta_of", c),
                (c, "partner_of", f"PadPartner_{i}"),
                (f"PadPartner_{i}", "meta_of", c),
                (f"PadDecoy_{i}", "works_at", f"PadDecoyCo_{i}"),
                (f"PadDecoyCo_{i}", "headquartered_in", f"PadDecoyCity_{i}"),
            ]
        )
    return edges


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    wiki = graph.records

    # pre-seal relation atoms
    for r in (
        "works_at",
        "headquartered_in",
        "owned_by",
        "partner_of",
        "meta_of",
        "in_state",
        "located_in",
    ):
        sealer.atom(r)

    edges: list[tuple[str, str, str]] = []
    for row in wiki:
        edges.extend(ceo_hq_edges(row))
    od = ROOT / "data/real_docs/opendata500_us_companies.csv"
    if od.exists():
        edges.extend(od500_edges(od))

    # unique
    seen = set()
    uniq = []
    for e in edges:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    edges = uniq

    lines: list[str] = []
    sealed_triples: list[tuple[str, str, str]] = []
    seen_edge: set[tuple[str, str, str]] = set()

    def append_edges(batch: list[tuple[str, str, str]]):
        for h, r, t in batch:
            key = (h, r, t)
            if key in seen_edge:
                continue
            seen_edge.add(key)
            sh, sr, st = sealer.triple(h, r, t)
            sealed_triples.append((sh, sr, st))
            lines.append(f"{sh} | {sr} | {st}")

    append_edges(edges)
    ctx = "\n".join(lines)
    tok = est_tokens(ctx)
    print(f"base triples={len(sealed_triples)} tokens~{tok}")

    pad_i = 0
    while tok < TARGET_TOKENS:
        batch_n = 2000
        append_edges(pad_chunk(pad_i, batch_n))
        pad_i += batch_n
        # incremental token estimate from line count * avg
        tok = est_tokens("\n".join(lines))
        if pad_i % 4000 == 0 or tok >= TARGET_TOKENS:
            print(f"pad_graphs={pad_i} triples={len(sealed_triples)} tokens~{tok}")

    # shuffle line order (and sealed list in same perm)
    order = list(range(len(lines)))
    rng.shuffle(order)
    lines = [lines[i] for i in order]
    sealed_triples = [sealed_triples[i] for i in order]
    ctx = "\n".join(lines)
    tok = est_tokens(ctx)

    router = SealRouter(sealed_triples)
    quiz = rng.sample(wiki, 8)

    cases = []
    buckets = {"NL": [], "PROG": [], "FOLLOW": [], "COMPLEX": []}

    for i, row in enumerate(quiz):
        person, company, hq = row["person"], row["company"], row["hq"]
        expect = sealer.atom(hq)
        co_seal = sealer.atom(company)
        p_seal = sealer.atom(person)
        r1, r2 = sealer.atom("works_at"), sealer.atom("headquartered_in")
        assert expect in router.path(p_seal, [r1, r2])

        # NL control
        q = f"Where is the headquarters of the company that {person} works_at?"
        cid = f"M1_NL_{i}"
        buckets["NL"].append((cid, raw_nl_program(f"QUESTION:\n{sealer.text(q)}")))
        cases.append({"id": cid, "form": "NL", "expect": expect, "company_seal": co_seal, "person": person, "hq": hq})

        # PROG binder
        prog = path_program(person, ("works_at", "headquartered_in"), hq).seal(sealer)
        cid = f"M1_PROG_{i}"
        buckets["PROG"].append((cid, prog))
        cases.append({"id": cid, "form": "PROG", "expect": expect, "company_seal": co_seal, "person": person, "hq": hq})

        # FOLLOW binder-dialog (relation seals in turns)
        body = (
            "DIALOG (answer FINAL HQ seal only)\n"
            f"USER_1: {sealer.text(f'Which company does {person} works_at?')}\n"
            f"USER_2: {sealer.text('Where is that company headquartered_in?')}\n"
        )
        cid = f"M1_FOLLOW_{i}"
        buckets["FOLLOW"].append((cid, raw_nl_program(body)))
        cases.append({"id": cid, "form": "FOLLOW", "expect": expect, "company_seal": co_seal, "person": person, "hq": hq})

        # COMPLEX binder PATH works_at → owned_by
        hold = f"Hold_{company}"
        prog3 = path_program(person, ("works_at", "owned_by"), hold).seal(sealer)
        expect3 = sealer.atom(hold)
        assert expect3 in router.path(p_seal, [sealer.atom("works_at"), sealer.atom("owned_by")])
        cid = f"M1_COMPLEX_{i}"
        buckets["COMPLEX"].append((cid, prog3))
        cases.append({"id": cid, "form": "COMPLEX", "expect": expect3, "company_seal": co_seal, "person": person, "target": hold})

    def pack(form: str, items) -> str:
        header = (
            f"MILLION-TOKEN sealed CONTEXT (~{tok} tok est). Form={form}. "
            "Binders kept. No decrypt. Answer every id."
        )
        parts = [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>",
            "",
            header,
            "",
            "===== SHARED CONTEXT BEGIN =====",
            ctx,
            "===== SHARED CONTEXT END =====",
            "",
            "Answer EACH id using ONLY the shared CONTEXT.",
            "",
        ]
        for cid, prog in items:
            parts.append(f"##### ID {cid} #####\n{prog.body}\n")
        return "\n".join(parts)

    RUNS.mkdir(parents=True, exist_ok=True)
    paths = {}
    for form, items in buckets.items():
        d = RUNS / f"{form}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        text = pack(form, items)
        p = d / "BATCH.txt"
        p.write_text(text)
        paths[form] = str(p)
        print(form, "bytes", p.stat().st_size, "file_tokens~", est_tokens(text))

    harness = {
        "target_tokens": TARGET_TOKENS,
        "context_tokens_est": tok,
        "context_chars": len(ctx),
        "n_triples": len(sealed_triples),
        "n_wiki": len(wiki),
        "n_quiz": len(quiz),
        "pad_graphs": pad_i,
        "paths": paths,
        "cases": cases,
        "claim": "Binders under ~1M-token sealed CONTEXT: PROG/FOLLOW/COMPLEX vs NL control",
        "rev": sealer.rev,
        "quiz_people": [r["person"] for r in quiz],
    }
    (RESULTS / "longctx_1m_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"tokens": tok, "triples": len(sealed_triples), "pad_graphs": pad_i}, indent=2))


if __name__ == "__main__":
    build()
