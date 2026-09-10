#!/usr/bin/env python3
"""Opacity × binder 2×2 on (A) CEO–HQ and (B) real 2WikiMultihopQA questions.

Missing cell vs locked three-arm: PLAIN_NL (readable symbols, no PATH).
If PLAIN_NL ≈ PLAIN_PROG ≈ SEAL_PROG ≫ SEAL_NL, opacity is the variable,
not “models cannot 2-hop without a plan.”

2Wiki items: human compositional questions + gold answers + Wikidata evidence
triples (Apache-2.0; cached at data/2wiki_compositional_n12.json).
SEAL_NL uses the same token sealer as the ceiling suite (not span-aware) so
tokenization mismatch is an acknowledged protocol confound, not a new arm.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter, lookup_program, path_program
from oir.adapters import ceo_hq_edges, load_ceo_hq_graph, load_csv_table

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "realqa_2x2"
KEY_CEO = b"oir-realqa-2x2-ceo-v1"
KEY_WIKI = b"oir-realqa-2x2-2wiki-v1"
KEY_WTQ = b"oir-realqa-2x2-wtq-v1"
SEED = 20260813
N_CEO = 12
N_WIKI = 12
N_WTQ = 8
WIKI_PATH = ROOT / "data" / "2wiki_compositional_n12.json"
WTQ_ROOT = ROOT / "data" / "benchmarks" / "WikiTableQuestions"
WTQ_IDS = [
    "nu-69",
    "nu-97",
    "nu-99",
    "nu-184",
    "nu-200",
    "nu-261",
    "nu-288",
    "nu-324",
]


def replace_spans(text: str, sealer: EntitySeal, atoms: list[str]) -> str:
    """Longest-first whole-span replace so start_seal can land in V(G)."""
    import re

    out = text
    for a in sorted({x for x in atoms if x}, key=len, reverse=True):
        variants = {a, a.replace("_", " ")}
        for v in sorted(variants, key=len, reverse=True):
            if len(v) < 3:
                continue
            out = re.sub(re.escape(v), sealer.atom(a), out, flags=re.I)
    return out


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


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


def write_arm(family: str, arm: str, kind: str, header: str, items) -> str:
    d = RUNS / family / f"{arm}_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "BATCH.txt"
    p.write_text(pack(kind, header, items))
    return str(p)


def build_ceo():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N_CEO)
    sealer = EntitySeal(KEY_CEO)
    buckets = {k: [] for k in ("PLAIN_NL", "PLAIN_PROG", "SEAL_NL", "SEAL_PROG", "SPAN_NL")}
    cases = []
    for i, row in enumerate(recs):
        person, hq, company = row["person"], row["hq"], row["company"]
        edges = ceo_hq_edges(row)
        plain_ctx = SealRouter(edges).render()
        sealed = [sealer.triple(*e) for e in edges]
        sealed_ctx = SealRouter(sealed).render()
        gold_seal = sealer.atom(hq)
        outs = SealRouter(sealed).path(
            sealer.atom(person),
            [sealer.atom("works_at"), sealer.atom("headquartered_in")],
        )
        assert list(dict.fromkeys(outs)) == [gold_seal], (outs, hq)

        q = (
            f"Where is the headquarters of the company that "
            f"{person.replace('_', ' ')} works for?"
        )
        prog = path_program(person, ("works_at", "headquartered_in"), hq)
        prog_s = prog.seal(sealer)
        prog_s.meta["start"] = sealer.atom(person)
        prog_s.meta["rels"] = [
            sealer.atom("works_at"),
            sealer.atom("headquartered_in"),
        ]
        ids = {
            "PLAIN_NL": f"CEO_PLAINNL_{i}",
            "PLAIN_PROG": f"CEO_PLAINPROG_{i}",
            "SEAL_NL": f"CEO_SEALNL_{i}",
            "SEAL_PROG": f"CEO_SEALPROG_{i}",
            "SPAN_NL": f"CEO_SPANNL_{i}",
        }
        q_span = replace_spans(
            q, sealer, [person, company, hq, "works_at", "headquartered_in"]
        )
        start_in_span = sealer.atom(person) in q_span
        buckets["PLAIN_NL"].append((ids["PLAIN_NL"], f"QUESTION:\n{q}", plain_ctx))
        buckets["PLAIN_PROG"].append((ids["PLAIN_PROG"], prog.body, plain_ctx))
        buckets["SEAL_NL"].append(
            (ids["SEAL_NL"], f"QUESTION:\n{sealer.text(q)}", sealed_ctx)
        )
        buckets["SEAL_PROG"].append((ids["SEAL_PROG"], prog_s.body, sealed_ctx))
        buckets["SPAN_NL"].append(
            (ids["SPAN_NL"], f"QUESTION:\n{q_span}", sealed_ctx)
        )
        cases.append(
            {
                "i": i,
                "person": person,
                "company": company,
                "hq": hq,
                "question": q,
                "ids": ids,
                "expect_plain": hq,
                "expect_seal": gold_seal,
                "start_seal_in_span_q": start_in_span,
                "source": "wikidata_ceo_hops_v2",
            }
        )
    headers = {
        "PLAIN_NL": "ARM CEO/PLAIN_NL: readable graph + English question. No PATH. Return the HQ city.",
        "PLAIN_PROG": "ARM CEO/PLAIN_PROG: readable graph + PATH binder.",
        "SEAL_NL": "ARM CEO/SEAL_NL: sealed graph + token-HMAC NL (ceiling protocol; start ID may not be in V(G)).",
        "SEAL_PROG": "ARM CEO/SEAL_PROG: sealed graph + PATH over seals.",
        "SPAN_NL": "ARM CEO/SPAN_NL: sealed graph + span-aligned NL (person/company/HQ/rel strings replaced as whole atoms). No PATH. start_seal should appear in QUESTION.",
    }
    kinds = {
        "PLAIN_NL": "plain",
        "PLAIN_PROG": "plain",
        "SEAL_NL": "sealed",
        "SEAL_PROG": "sealed",
        "SPAN_NL": "sealed",
    }
    paths = {
        arm: write_arm("ceo", arm, kinds[arm], headers[arm], buckets[arm])
        for arm in buckets
    }
    return {
        "n": N_CEO,
        "seed": SEED,
        "family": "ceo_hq",
        "source": "data/real/wikidata_ceo_hops_v2.json",
        "question_form": "Where is the headquarters of the company that {person} works for?",
        "gold": "Wikidata HQ city (exact)",
        "paths": paths,
        "cases": cases,
        "sealrouter_ceiling": f"{N_CEO}/{N_CEO}",
        "protocol_note": (
            "SEAL_NL = EntitySeal.text (token HMAC; start ID may not be in V(G)). "
            "SPAN_NL = whole-span replace of person/company/HQ/relations so start_seal ∈ QUESTION."
        ),
    }


def build_2wiki():
    items = json.loads(WIKI_PATH.read_text())["items"][:N_WIKI]
    sealer = EntitySeal(KEY_WIKI)
    # Shared graph: all evidence triples so each quiz is a walk in a mixed KG.
    all_edges = []
    for it in items:
        for h, r, t in it["evidences"]:
            all_edges.append((h, r, t))
    plain_ctx = SealRouter(all_edges).render()
    sealed_edges = [sealer.triple(*e) for e in all_edges]
    sealed_ctx = SealRouter(sealed_edges).render()

    buckets = {k: [] for k in ("PLAIN_NL", "PLAIN_PROG", "SEAL_NL", "SEAL_PROG", "SPAN_NL")}
    cases = []
    for i, it in enumerate(items):
        ev = it["evidences"]
        start, r1, mid = ev[0]
        _mid, r2, gold = ev[1]
        assert _mid == mid
        gold_seal = sealer.atom(gold)
        outs = SealRouter(sealed_edges).path(
            sealer.atom(start), [sealer.atom(r1), sealer.atom(r2)]
        )
        assert list(dict.fromkeys(outs)) == [gold_seal], (it["id"], outs, gold)

        q = it["question"]
        prog = path_program(start, (r1, r2), gold)
        prog_s = prog.seal(sealer)
        prog_s.meta["start"] = sealer.atom(start)
        prog_s.meta["rels"] = [sealer.atom(r1), sealer.atom(r2)]
        ids = {
            "PLAIN_NL": f"WIKI_PLAINNL_{i}",
            "PLAIN_PROG": f"WIKI_PLAINPROG_{i}",
            "SEAL_NL": f"WIKI_SEALNL_{i}",
            "SEAL_PROG": f"WIKI_SEALPROG_{i}",
            "SPAN_NL": f"WIKI_SPANNL_{i}",
        }
        q_span = replace_spans(q, sealer, [start, mid, gold])  # entities only; do not paste PATH into Q
        start_in_span = sealer.atom(start) in q_span
        buckets["PLAIN_NL"].append((ids["PLAIN_NL"], f"QUESTION:\n{q}", plain_ctx))
        buckets["PLAIN_PROG"].append((ids["PLAIN_PROG"], prog.body, plain_ctx))
        buckets["SEAL_NL"].append(
            (ids["SEAL_NL"], f"QUESTION:\n{sealer.text(q)}", sealed_ctx)
        )
        buckets["SEAL_PROG"].append((ids["SEAL_PROG"], prog_s.body, sealed_ctx))
        buckets["SPAN_NL"].append(
            (ids["SPAN_NL"], f"QUESTION:\n{q_span}", sealed_ctx)
        )
        cases.append(
            {
                "i": i,
                "wiki_id": it["id"],
                "question": q,
                "answer": gold,
                "start": start,
                "rels": [r1, r2],
                "mid": mid,
                "ids": ids,
                "expect_plain": gold,
                "expect_seal": gold_seal,
                "start_seal_in_span_q": start_in_span,
                "source": "2WikiMultihopQA validation compositional",
            }
        )
    headers = {
        "PLAIN_NL": (
            "ARM 2WIKI/PLAIN_NL: real compositional question (2WikiMultihopQA) + "
            "plaintext evidence KG. No PATH. Return the gold answer string."
        ),
        "PLAIN_PROG": "ARM 2WIKI/PLAIN_PROG: same KG + gold PATH over readable symbols.",
        "SEAL_NL": "ARM 2WIKI/SEAL_NL: sealed KG + token-HMAC NL (start ID may not be in V(G)).",
        "SEAL_PROG": "ARM 2WIKI/SEAL_PROG: sealed KG + PATH over seals.",
        "SPAN_NL": "ARM 2WIKI/SPAN_NL: sealed KG + entity-span NL (start/mid/answer strings replaced as whole atoms; relation words left in English). No PATH.",
    }
    kinds = {
        "PLAIN_NL": "plain",
        "PLAIN_PROG": "plain",
        "SEAL_NL": "sealed",
        "SEAL_PROG": "sealed",
        "SPAN_NL": "sealed",
    }
    paths = {
        arm: write_arm("wiki", arm, kinds[arm], headers[arm], buckets[arm])
        for arm in buckets
    }
    return {
        "n": N_WIKI,
        "family": "2wiki_compositional",
        "source": str(WIKI_PATH.relative_to(ROOT)),
        "license": "Apache-2.0 (2WikiMultihopQA)",
        "gold": "dataset answer string; sealed arm = HMAC of that string",
        "paths": paths,
        "cases": cases,
        "sealrouter_ceiling": f"{N_WIKI}/{N_WIKI}",
        "protocol_note": (
            "Questions and answers are the dataset's. Context is the union of the "
            "12 gold evidence chains (24 triples), not Wikipedia passages. "
            "SEAL_NL = EntitySeal.text. SPAN_NL = whole-span entity/relation replace; "
            "log start_seal_in_span_q. Unique path: SPAN_NL success may be copy-and-walk."
        ),
    }


def build_wtq():
    import csv

    index = {}
    with (WTQ_ROOT / "data" / "pristine-unseen-tables.tsv").open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            index[row["id"]] = row
    sealer = EntitySeal(KEY_WTQ)
    buckets = {k: [] for k in ("PLAIN_NL", "PLAIN_PROG", "SEAL_NL", "SEAL_PROG")}
    cases = []
    for i, tid in enumerate(WTQ_IDS):
        rec = index[tid]
        gold = rec["targetValue"].split("|")[0].strip()
        q = rec["utterance"]
        table = load_csv_table(WTQ_ROOT / rec["context"])
        hits = table.find_answer_cells(gold)
        assert len(hits) == 1, (tid, hits, gold)
        row_id, col_rel, val_atom = hits[0]
        rel_headers = [
            f"col_{EntitySeal.normalize(str(h)) or f'COL_{ci}'}"
            for ci, h in enumerate(table.header)
        ]
        headers = ["row_id", *rel_headers]
        plain_rows, seal_rows = [], []
        for ri, row in enumerate(table.rows, start=1):
            rid = f"ROW_{ri}"
            cells = [str(c).strip() for c in row]
            while len(cells) < len(table.header):
                cells.append("")
            cells = cells[: len(table.header)]
            plain_rows.append([rid, *cells])
            seal_rows.append(
                [sealer.atom(rid), *[sealer.atom(c) if c else sealer.atom("EMPTY") for c in cells]]
            )
        plain_tbl = md_table(headers, plain_rows)
        seal_tbl = md_table([sealer.atom(h) for h in headers], seal_rows)
        gold_seal = sealer.atom(gold)
        prog = lookup_program(row_id, col_rel, gold)
        prog_s = prog.seal(sealer)
        prog_s.meta["row"] = sealer.atom(row_id)
        prog_s.meta["col"] = sealer.atom(col_rel)
        outs = SealRouter(
            [(sealer.atom(h), sealer.atom(r), sealer.atom(t)) for h, r, t in table.triples()]
        ).lookup(sealer.atom(row_id), sealer.atom(col_rel))
        assert list(dict.fromkeys(outs)) == [gold_seal], (tid, outs, gold, val_atom)

        ids = {
            "PLAIN_NL": f"WTQ_PLAINNL_{i}",
            "PLAIN_PROG": f"WTQ_PLAINPROG_{i}",
            "SEAL_NL": f"WTQ_SEALNL_{i}",
            "SEAL_PROG": f"WTQ_SEALPROG_{i}",
        }
        buckets["PLAIN_NL"].append((ids["PLAIN_NL"], f"QUESTION:\n{q}", plain_tbl))
        buckets["PLAIN_PROG"].append((ids["PLAIN_PROG"], prog.body, plain_tbl))
        buckets["SEAL_NL"].append(
            (ids["SEAL_NL"], f"QUESTION:\n{sealer.text(q)}", seal_tbl)
        )
        buckets["SEAL_PROG"].append((ids["SEAL_PROG"], prog_s.body, seal_tbl))
        cases.append(
            {
                "i": i,
                "wtq_id": tid,
                "question": q,
                "answer": gold,
                "csv": rec["context"],
                "row_id": row_id,
                "col_rel": col_rel,
                "ids": ids,
                "expect_plain": gold,
                "expect_seal": gold_seal,
                "source": "WikiTableQuestions pristine-unseen-tables",
            }
        )
    headers = {
        "PLAIN_NL": (
            "ARM WTQ/PLAIN_NL: real WikiTableQuestions utterance + markdown table. "
            "No LOOKUP. Return the table cell that answers the question."
        ),
        "PLAIN_PROG": "ARM WTQ/PLAIN_PROG: same table + gold LOOKUP(row, col).",
        "SEAL_NL": "ARM WTQ/SEAL_NL: sealed table + sealed NL. No LOOKUP.",
        "SEAL_PROG": "ARM WTQ/SEAL_PROG: sealed table + LOOKUP over seals.",
    }
    kinds = {
        "PLAIN_NL": "plain",
        "PLAIN_PROG": "plain",
        "SEAL_NL": "sealed",
        "SEAL_PROG": "sealed",
    }
    paths = {
        arm: write_arm("wtq", arm, kinds[arm], headers[arm], buckets[arm])
        for arm in buckets
    }
    return {
        "n": N_WTQ,
        "family": "wtq_lookup",
        "source": "data/benchmarks/WikiTableQuestions",
        "license": "CC BY-SA 4.0 (WikiTableQuestions)",
        "ids": WTQ_IDS,
        "gold": "dataset targetValue (unique body cell)",
        "paths": paths,
        "cases": cases,
        "sealrouter_ceiling": f"{N_WTQ}/{N_WTQ}",
        "protocol_note": (
            "PLAIN_NL uses the human question. PROG is gold cell LOOKUP (binder control), "
            "not a WTQ semantic parser. Some questions are mildly compositional "
            "(first/last/only); do not claim a WTQ leaderboard."
        ),
    }


def build():
    RUNS.mkdir(parents=True, exist_ok=True)
    ceo = build_ceo()
    wiki = build_2wiki()
    wtq = build_wtq()
    harness = {
        "suite": "realqa_2x2",
        "design": "opacity × binder: PLAIN_NL / PLAIN_PROG / SEAL_NL / SEAL_PROG",
        "prediction": "PLAIN_NL ≈ PLAIN_PROG ≈ SEAL_PROG ≫ SEAL_NL",
        "nonclaim": (
            "Not G-Rev1. Not privacy. 2Wiki context is gold evidence triples, "
            "not full Wikipedia retrieval. WTQ PROG is gold LOOKUP, not a WTQ solver. "
            "Spider join-SQL lock is still missing. "
            "SEAL_NL token-HMAC is the ceiling protocol (start ID may leave V(G)); "
            "SPAN_NL is the span-aligned control. PLAIN_NL is not counterfactual — "
            "parametric Wikipedia answers remain possible."
        ),
        "ceo": ceo,
        "wiki": wiki,
        "wtq": wtq,
    }
    out = RESULTS / "realqa_2x2_harness.json"
    out.write_text(json.dumps(harness, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {"ceo_n": ceo["n"], "wiki_n": wiki["n"], "wtq_n": wtq["n"], "out": str(out)},
            indent=2,
        )
    )
    print("wrote", out)


if __name__ == "__main__":
    build()
