#!/usr/bin/env python3
"""
WTQ binder fix: sealed cell-LOOKUP DSL vs sealed NL (already 0/20).

For each WikiTableQuestions item where the answer cell is in the sealed table,
emit an explicit SEALED_DSL that names (row_id, col_rel) — model only executes.
This tests whether complex-table failure is missing program, not missing capability.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "wtq_dsl"
BENCH = ROOT / "data/benchmarks/WikiTableQuestions"
KEY = b"oir-wtq-dsl-v1"
H_COMPLEX = json.loads((RESULTS / "complex_bench_harness.json").read_text())


class EntitySeal:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def atom(self, a: str) -> str:
        a = re.sub(r"\s+", "_", str(a).strip())
        a = re.sub(r"[^A-Za-z0-9_.\-]+", "_", a).strip("_") or "EMPTY"
        if len(a) > 48:
            a = a[:48]
        if a not in self.fwd:
            d = hmac.new(self.key, a.encode(), hashlib.sha256).digest()
            t = "E" + d[:6].hex()
            self.fwd[a] = t
            self.rev[t] = a
        return self.fwd[a]

    def text(self, s: str) -> str:
        return "".join(
            self.atom(p) if re.fullmatch(r"[A-Za-z0-9_.\-]+", p) else p
            for p in re.findall(r"[A-Za-z0-9_.\-]+|[^A-Za-z0-9_.\-]+", s)
        )


def atomize(s: str) -> str:
    s = re.sub(r"\s+", "_", str(s).strip())
    s = re.sub(r"[^A-Za-z0-9_.\-]+", "_", s).strip("_")
    return (s[:48] if s else "EMPTY")


def table_edges(table, max_rows=20):
    header = [str(c) for c in table[0]]
    edges = []
    cells = {}  # (ri,ci) -> (row_id, rel, val_atom)
    for ri, row in enumerate(table[1 : max_rows + 1], start=1):
        row_id = f"ROW_{ri}"
        for ci, cell in enumerate(row):
            if ci >= len(header):
                break
            col = atomize(header[ci]) or f"COL_{ci}"
            val = str(cell).strip()
            if not val or val.lower() in ("none", "null", "-"):
                continue
            va = atomize(val)
            rel = f"col_{col}"
            edges.append((row_id, rel, va))
            cells[(ri, ci)] = (row_id, rel, va, val)
    return edges, cells, header


def find_answer_cell(cells, target: str):
    tgt = atomize(target.split("|")[0].strip())
    # also try raw lower match on display val
    hits = []
    for (ri, ci), (row_id, rel, va, val) in cells.items():
        if va == tgt or val.strip() == target.split("|")[0].strip():
            hits.append((ri, ci, row_id, rel, va))
    return hits


def write_batch(name, header, items):
    d = RUNS / f"{name}_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        header + "\n",
    ]
    for cid, body in items:
        lines.append(f"\n##### ID {cid} #####\n{body}\n")
    (d / "BATCH.txt").write_text("\n".join(lines))
    return str(d / "BATCH.txt")


def main():
    sealer = EntitySeal(KEY)
    wtq = [c for c in H_COMPLEX["cases"] if c["bench"] == "WikiTableQuestions"]
    dsl_items, nl_items, cases = [], [], []
    n_prog = 0
    for i, ex in enumerate(wtq):
        with open(ex["table_path"], newline="", encoding="utf-8", errors="replace") as f:
            table = list(csv.reader(f))
        edges, cells, header = table_edges(table)
        hits = find_answer_cell(cells, ex["target"])
        ctx = "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)
        expect = sealer.atom(atomize(ex["target"].split("|")[0].strip()))
        cid_nl = f"WTQFIX_NL_{i}"
        nl_items.append(
            (
                cid_nl,
                f"STRATUM: {ex['stratum']}\nQUESTION:\n{sealer.text(ex['question'])}\n\nCONTEXT:\n{ctx}",
            )
        )
        cases.append(
            {
                "id": cid_nl,
                "form": "NL",
                "stratum": ex["stratum"],
                "expect": expect,
                "in_ctx": bool(hits),
                "question": ex["question"],
                "target": ex["target"],
            }
        )
        if not hits:
            continue
        # take first hit; build LOOKUP(row, col)
        ri, ci, row_id, rel, va = hits[0]
        dsl = (
            "SEALED_DSL\n"
            f"ROW {sealer.atom(row_id)}\n"
            f"COL {sealer.atom(rel)}\n"
            f"RETURN LOOKUP(ROW, COL)\n"
            "Execute exact triple match in CONTEXT."
        )
        cid = f"WTQFIX_DSL_{i}"
        dsl_items.append((cid, f"STRATUM: {ex['stratum']}\n{dsl}\n\nCONTEXT:\n{ctx}"))
        cases.append(
            {
                "id": cid,
                "form": "DSL",
                "stratum": ex["stratum"],
                "expect": expect,
                "in_ctx": True,
                "row": row_id,
                "rel": rel,
                "question": ex["question"],
                "target": ex["target"],
            }
        )
        n_prog += 1
        assert sealer.atom(va) == expect or expect == sealer.atom(va)

    paths = {
        "WTQFIX_NL": write_batch("WTQFIX_NL", "WTQ sealed NL control (rerun).", nl_items),
        "WTQFIX_DSL": write_batch("WTQFIX_DSL", "WTQ sealed cell-LOOKUP DSL (binder fix).", dsl_items),
    }
    harness = {
        "n_nl": len(nl_items),
        "n_dsl": len(dsl_items),
        "paths": paths,
        "cases": cases,
        "rev": sealer.rev,
        "claim": "WTQ sealed NL fails; explicit cell LOOKUP DSL restores answers when cell is in table",
    }
    (RESULTS / "wtq_dsl_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n_nl": len(nl_items), "n_dsl": n_prog, "paths": paths}, indent=2))


if __name__ == "__main__":
    main()
