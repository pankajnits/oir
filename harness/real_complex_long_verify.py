#!/usr/bin/env python3
"""
CROSS-VERIFY (user ask): large sealed CONTEXT + *real* complex questions.

Not CEO PATH needles in pad hay. Real FinQA L3+ compose + WTQ compose/aggregate
tables and questions. Research path = gold PROG / cell LOOKUP DSL vs sealed NL.
Optional sealed follow-up on the same FinQA table.

Context = many real FinQA+WTQ tables sealed together (large shared CONTEXT).
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from complex_bench import (  # noqa: E402
    EntitySeal,
    atomize,
    finqa_depth,
    load_wtq,
    render_edges,
    table_to_kv_edges,
)

BENCH = ROOT / "data" / "benchmarks"
RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "real_complex_verify"
KEY = b"oir-real-complex-verify-v1"
SEED = 20260728
TARGET_TOKENS = 80_000  # large; prefer real tables over pad
N_QUIZ_FQ = 8
N_QUIZ_WTQ = 6
N_FOLLOW = 4


def est_tok(s: str) -> int:
    return max(1, len(s) // 4)


def load_finqa_hard(n_quiz: int, n_filler: int, rng: random.Random):
    path = BENCH / "FinQA" / "dataset" / "train.json"
    data = json.loads(path.read_text())
    hard, any_ok = [], []
    for ex in data:
        qa = ex.get("qa") or {}
        if not qa.get("question") or not qa.get("program") or not ex.get("table") or len(ex["table"]) < 2:
            continue
        ans = qa.get("exe_ans", qa.get("answer"))
        if ans is None:
            continue
        depth = finqa_depth(qa["program"])
        item = {
            "id": ex["id"],
            "question": qa["question"],
            "program": qa["program"],
            "exe_ans": ans,
            "table": ex["table"],
            "depth": depth,
            "stratum": "L3plus_compose" if depth >= 3 else ("L2_two_op" if depth == 2 else "L1"),
        }
        any_ok.append(item)
        if depth >= 3:
            hard.append(item)
    rng.shuffle(hard)
    rng.shuffle(any_ok)
    quiz = hard[:n_quiz]
    # filler = other real tables (exclude quiz ids)
    qids = {x["id"] for x in quiz}
    filler = [x for x in any_ok if x["id"] not in qids][:n_filler]
    return quiz, filler


def load_wtq_complex(n: int, rng: random.Random):
    # reuse loader then filter compose/aggregate with answer in table
    all_ex = load_wtq(n * 8, rng)
    out = []
    for ex in all_ex:
        if ex["stratum"] not in ("compose", "aggregate", "compare"):
            continue
        with open(ex["table_path"], newline="", encoding="utf-8", errors="replace") as f:
            table = list(csv.reader(f))
        edges, cell_map = table_to_kv_edges(table, max_rows=20, seal_numbers=True)
        # find answer cell
        tgt = atomize(ex["target"].split("|")[0].strip())
        hits = []
        for (ri, ci), val in cell_map.items():
            if atomize(val) == tgt or val.strip() == ex["target"].split("|")[0].strip():
                hits.append((f"ROW_{ri}", f"col_{atomize(table[0][ci]) if ci < len(table[0]) else f'COL_{ci}'}", atomize(val)))
        if not hits:
            continue
        ex = dict(ex)
        ex["table"] = table
        ex["edges"] = edges
        ex["hit"] = hits[0]
        out.append(ex)
        if len(out) >= n:
            break
    return out


def seal_table_block(sealer: EntitySeal, doc_id: str, table, seal_numbers: bool) -> str:
    edges, _ = table_to_kv_edges(table, max_rows=15, seal_numbers=seal_numbers)
    # namespace rows with doc id to avoid ROW_1 collisions across tables
    named = []
    for h, r, t in edges:
        named.append((f"{doc_id}_{h}", r, t))
    body = render_edges(sealer, named, passthrough_num=not seal_numbers)
    return f"### TABLE {sealer.atom(doc_id)} ###\n{body}"


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)

    # Real FinQA: quiz = hardest; filler = many real tables
    fq_quiz, fq_filler = load_finqa_hard(N_QUIZ_FQ, 400, rng)
    wtq_quiz = load_wtq_complex(N_QUIZ_WTQ, rng)

    blocks = []
    # filler first (hay), quiz tables included too (needles must be in C)
    for i, ex in enumerate(fq_filler):
        blocks.append(seal_table_block(sealer, f"FQF_{i}_{ex['id'][:24]}", ex["table"], seal_numbers=False))
    for i, ex in enumerate(fq_quiz):
        blocks.append(seal_table_block(sealer, f"FQQ_{i}_{ex['id'][:24]}", ex["table"], seal_numbers=False))
    for i, ex in enumerate(wtq_quiz):
        blocks.append(seal_table_block(sealer, f"WTQ_{i}_{ex['id'][:24]}", ex["table"], seal_numbers=True))

    ctx = "\n\n".join(blocks)
    tok = est_tok(ctx)
    print(f"real-only context tokens~{tok} blocks={len(blocks)}")

    # If under target, add more FinQA train tables (still real)
    if tok < TARGET_TOKENS:
        more_path = BENCH / "FinQA" / "dataset" / "train.json"
        more = json.loads(more_path.read_text())
        rng.shuffle(more)
        used = {x["id"] for x in fq_quiz + fq_filler}
        j = 0
        for ex in more:
            if tok >= TARGET_TOKENS:
                break
            if ex["id"] in used or not ex.get("table"):
                continue
            blocks.append(seal_table_block(sealer, f"FQX_{j}_{ex['id'][:20]}", ex["table"], seal_numbers=False))
            j += 1
            if j % 50 == 0:
                ctx = "\n\n".join(blocks)
                tok = est_tok(ctx)
                print(f"  +{j} tables tokens~{tok}")
        ctx = "\n\n".join(blocks)
        tok = est_tok(ctx)

    print(f"FINAL tokens~{tok} tables={len(blocks)}")

    cases = []
    buckets = {"FQ_NL": [], "FQ_PROG": [], "FQ_FOLLOW": [], "WTQ_NL": [], "WTQ_DSL": []}

    # --- FinQA quiz ---
    for i, ex in enumerate(fq_quiz):
        doc = f"FQQ_{i}_{ex['id'][:24]}"
        # NL
        cid = f"RCV_FQ_NL_{i}"
        body = (
            f"ANSWER_MODE: ANSWER_NUM\n"
            f"TABLE_ID: {sealer.atom(doc)}\n"
            f"QUESTION:\n{sealer.text(ex['question'])}\n"
            "Compute using CONTEXT numbers for this TABLE_ID. Reply ANSWER_NUM[<id>]: <number>"
        )
        buckets["FQ_NL"].append((cid, body))
        cases.append(
            {
                "id": cid,
                "form": "FQ_NL",
                "expect_num": float(ex["exe_ans"]) if not isinstance(ex["exe_ans"], bool) else ex["exe_ans"],
                "stratum": ex["stratum"],
                "depth": ex["depth"],
                "question": ex["question"],
                "program": ex["program"],
                "src": ex["id"],
            }
        )
        # PROG research path
        cid = f"RCV_FQ_PROG_{i}"
        body = (
            f"ANSWER_MODE: ANSWER_NUM\n"
            f"TABLE_ID: {sealer.atom(doc)}\n"
            f"FINQA_PROGRAM (ops+numbers plaintext; use CONTEXT if needed):\n{ex['program']}\n"
            "Execute program. Reply ANSWER_NUM[<id>]: <number>"
        )
        buckets["FQ_PROG"].append((cid, body))
        cases.append(
            {
                "id": cid,
                "form": "FQ_PROG",
                "expect_num": float(ex["exe_ans"]) if not isinstance(ex["exe_ans"], bool) else ex["exe_ans"],
                "stratum": ex["stratum"],
                "depth": ex["depth"],
                "question": ex["question"],
                "program": ex["program"],
                "src": ex["id"],
            }
        )

    # Follow-ups: second question on same table — ask for first intermediate if multi-op,
    # else rephrase "confirm the program result"
    for i, ex in enumerate(fq_quiz[:N_FOLLOW]):
        doc = f"FQQ_{i}_{ex['id'][:24]}"
        cid = f"RCV_FQ_FOLLOW_{i}"
        # sealed dialog: Q1 sealed NL (hard), Q2 binder program for same table
        body = (
            "DIALOG — answer FINAL only (ANSWER_NUM)\n"
            f"TABLE_ID: {sealer.atom(doc)}\n"
            f"USER_1: {sealer.text(ex['question'])}\n"
            f"USER_2: Execute this program on the same table and return the number:\n{ex['program']}\n"
            "Reply ANSWER_NUM[<id>]: <number> for USER_2 final."
        )
        buckets["FQ_FOLLOW"].append((cid, body))
        cases.append(
            {
                "id": cid,
                "form": "FQ_FOLLOW",
                "expect_num": float(ex["exe_ans"]) if not isinstance(ex["exe_ans"], bool) else ex["exe_ans"],
                "stratum": ex["stratum"],
                "question": ex["question"],
                "program": ex["program"],
                "src": ex["id"],
                "note": "follow-up supplies gold program binder after sealed NL turn",
            }
        )

    # --- WTQ complex ---
    for i, ex in enumerate(wtq_quiz):
        doc = f"WTQ_{i}_{ex['id'][:24]}"
        row_id, col_rel, val_atom = ex["hit"]
        # remap row with doc prefix as in context
        row_full = f"{doc}_{row_id}"
        expect = sealer.atom(val_atom)
        cid = f"RCV_WTQ_NL_{i}"
        body = (
            f"ANSWER_MODE: ANSWER_SEALED\n"
            f"TABLE_ID: {sealer.atom(doc)}\n"
            f"QUESTION:\n{sealer.text(ex['question'])}\n"
            "Reply ANSWER_SEALED[<id>]: <cell_seal>"
        )
        buckets["WTQ_NL"].append((cid, body))
        cases.append(
            {
                "id": cid,
                "form": "WTQ_NL",
                "expect": expect,
                "stratum": ex["stratum"],
                "question": ex["question"],
                "target": ex["target"],
                "src": ex["id"],
            }
        )
        cid = f"RCV_WTQ_DSL_{i}"
        body = (
            f"ANSWER_MODE: ANSWER_SEALED\n"
            f"TABLE_ID: {sealer.atom(doc)}\n"
            f"SEALED_DSL\nROW {sealer.atom(row_full)}\nCOL {sealer.atom(col_rel)}\n"
            f"RETURN LOOKUP(ROW, COL)\n"
            "Execute exact match in this TABLE_ID block."
        )
        buckets["WTQ_DSL"].append((cid, body))
        cases.append(
            {
                "id": cid,
                "form": "WTQ_DSL",
                "expect": expect,
                "stratum": ex["stratum"],
                "question": ex["question"],
                "target": ex["target"],
                "src": ex["id"],
            }
        )

    def pack(form: str, items: list, header: str) -> str:
        parts = [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
            "Real FinQA + WikiTableQuestions tables in SHARED CONTEXT.",
            "Research path: binders (PROG/DSL) vs sealed NL.",
            header,
            "",
            "===== SHARED CONTEXT BEGIN (real tables) =====",
            ctx,
            "===== SHARED CONTEXT END =====",
            "",
        ]
        for cid, body in items:
            parts.append(f"##### ID {cid} #####\n{body}\n")
        return "\n".join(parts)

    RUNS.mkdir(parents=True, exist_ok=True)
    paths = {}
    headers = {
        "FQ_NL": "FinQA L3+ real questions, sealed NL, large real CONTEXT.",
        "FQ_PROG": "FinQA L3+ gold PROGRAM binder (research path).",
        "FQ_FOLLOW": "FinQA sealed NL turn then PROGRAM follow-up binder.",
        "WTQ_NL": "WTQ complex real questions, sealed NL.",
        "WTQ_DSL": "WTQ gold cell LOOKUP DSL binder (research path).",
    }
    for form, items in buckets.items():
        if not items:
            continue
        d = RUNS / f"{form}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        text = pack(form, items, headers[form])
        p = d / "BATCH.txt"
        p.write_text(text)
        paths[form] = str(p)
        print(form, "n=", len(items), "bytes", p.stat().st_size, "tok~", est_tok(text))

    harness = {
        "context_tokens_est": tok,
        "n_tables": len(blocks),
        "n_fq_quiz": len(fq_quiz),
        "n_wtq_quiz": len(wtq_quiz),
        "paths": paths,
        "cases": cases,
        "claim": (
            "Cross-verify: real complex FinQA/WTQ questions in large sealed real-table CONTEXT; "
            "research binders vs sealed NL."
        ),
        "rev": sealer.rev,
        "fq_programs": [{"id": c["id"], "program": c.get("program"), "q": c.get("question")} for c in cases if c["form"] == "FQ_PROG"],
    }
    (RESULTS / "real_complex_verify_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"tokens": tok, "tables": len(blocks), "paths": list(paths)}, indent=2))


if __name__ == "__main__":
    build()
