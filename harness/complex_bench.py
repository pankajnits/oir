#!/usr/bin/env python3
"""
Complex real-benchmark OIR pilot.

Sources:
  - FinQA: financial tables + gold reasoning programs (NL vs PROG)
  - WikiTableQuestions: complex questions over real Wikipedia tables → big Excel

Stratifies FinQA by program operator depth; WTQ by question heuristics.
Exports large Excel workbooks + PDF text dumps; builds sealed NL vs PROG batches.
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
BENCH = ROOT / "data" / "benchmarks"
OUT = ROOT / "data" / "real_docs" / "complex"
RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "complex_bench"
KEY = b"oir-complex-bench-v1"
SEED = 20260727
N_FINQA = 20
N_WTQ = 20

try:
    from openpyxl import Workbook
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl", "-q"])
    from openpyxl import Workbook


class EntitySeal:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def atom(self, a: str) -> str:
        a = re.sub(r"\s+", "_", str(a).strip())
        a = re.sub(r"[^A-Za-z0-9_.\-]+", "_", a).strip("_")
        if not a:
            a = "EMPTY"
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


def write_xlsx(path: Path, sheets: dict[str, list[list]]):
    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(re.sub(r"[\\/*?\[\]]", "_", title)[:31])
        for row in rows:
            ws.append([("" if c is None else c) for c in row])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def finqa_depth(program: str) -> int:
    # count operators roughly
    ops = re.findall(r"\b(add|subtract|multiply|divide|exp|greater|table_sum|table_average|table_max|table_min)\b", program or "", re.I)
    return max(1, len(ops))


def stratum_from_depth(d: int) -> str:
    if d <= 1:
        return "L1_single_op"
    if d == 2:
        return "L2_two_op"
    return "L3plus_compose"


def load_finqa(n: int, rng: random.Random):
    path = BENCH / "FinQA" / "dataset" / "dev.json"
    data = json.loads(path.read_text())
    usable = []
    for ex in data:
        qa = ex.get("qa") or {}
        if not qa.get("question") or not qa.get("program"):
            continue
        if not ex.get("table") or len(ex["table"]) < 2:
            continue
        # prefer numeric exe_ans
        ans = qa.get("exe_ans", qa.get("answer"))
        if ans is None:
            continue
        depth = finqa_depth(qa["program"])
        usable.append(
            {
                "id": ex["id"],
                "question": qa["question"],
                "program": qa["program"],
                "exe_ans": ans,
                "table": ex["table"],
                "depth": depth,
                "stratum": stratum_from_depth(depth),
                "pre_text": (ex.get("pre_text") or [])[:3],
                "post_text": (ex.get("post_text") or [])[:2],
            }
        )
    rng.shuffle(usable)
    # stratified sample
    by = {}
    for u in usable:
        by.setdefault(u["stratum"], []).append(u)
    out = []
    per = max(1, n // 3)
    for s in ("L1_single_op", "L2_two_op", "L3plus_compose"):
        out.extend(by.get(s, [])[:per])
    while len(out) < n and usable:
        for u in usable:
            if u not in out:
                out.append(u)
            if len(out) >= n:
                break
    return out[:n]


def load_wtq(n: int, rng: random.Random):
    tsv = BENCH / "WikiTableQuestions" / "data" / "pristine-unseen-tables.tsv"
    # fallback training
    if not tsv.exists():
        tsv = BENCH / "WikiTableQuestions" / "data" / "training.tsv"
    rows = list(csv.DictReader(tsv.open(), delimiter="\t"))
    # columns: id, utterance, context, targetValue (varies) — check
    # WTQ format: id \t utterance \t context \t targetValue
    examples = []
    for r in rows:
        keys = {k.lower(): k for k in r}
        utt = r.get("utterance") or r.get(keys.get("utterance", ""), "")
        ctx = r.get("context") or r.get(keys.get("context", ""), "")
        tgt = r.get("targetValue") or r.get(keys.get("targetvalue", ""), "")
        eid = r.get("id") or r.get(keys.get("id", ""), "")
        if not utt or not ctx or not tgt:
            continue
        # context like csv/204-csv/78.csv
        table_path = BENCH / "WikiTableQuestions" / ctx
        if not table_path.exists():
            continue
        # complexity heuristic
        q = utt.lower()
        if any(w in q for w in ("how many", "total", "average", "sum")):
            stratum = "aggregate"
        elif any(w in q for w in ("which", "what", "who")) and ("than" in q or "most" in q or "least" in q or "highest" in q or "lowest" in q):
            stratum = "compare"
        elif " and " in q or " or " in q or "both" in q:
            stratum = "compose"
        else:
            stratum = "lookup_filter"
        examples.append(
            {
                "id": eid,
                "question": utt,
                "target": tgt,
                "table_path": str(table_path),
                "stratum": stratum,
            }
        )
    rng.shuffle(examples)
    by = {}
    for e in examples:
        by.setdefault(e["stratum"], []).append(e)
    out = []
    for s in ("lookup_filter", "compare", "aggregate", "compose"):
        out.extend(by.get(s, [])[: max(1, n // 4)])
    while len(out) < n:
        for e in examples:
            if e not in out:
                out.append(e)
            if len(out) >= n:
                break
        break
    return out[:n]


def table_to_kv_edges(table: list[list], max_rows=12, seal_numbers: bool = True):
    """Convert table to row-keyed triples. Numbers can stay plaintext for FinQA arithmetic."""
    if not table:
        return [], {}
    header = [str(c) for c in table[0]]
    edges = []
    cell_map = {}
    for ri, row in enumerate(table[1 : max_rows + 1], start=1):
        row_id = f"ROW_{ri}"
        for ci, cell in enumerate(row):
            if ci >= len(header):
                break
            col = atomize(header[ci]) or f"COL_{ci}"
            val = str(cell).strip()
            if not val or val.lower() in ("none", "null", "-"):
                continue
            is_num = bool(re.fullmatch(r"[-+]?\d*\.?\d+%?", val.replace(",", "")))
            if is_num and not seal_numbers:
                edges.append((row_id, f"col_{col}", f"NUM_{val.replace(',', '').replace('%', 'pct')}"))
            else:
                edges.append((row_id, f"col_{col}", atomize(val) or val))
            cell_map[(ri, ci)] = val
    return edges, cell_map


def atomize(s: str) -> str:
    s = re.sub(r"\s+", "_", str(s).strip())
    s = re.sub(r"[^A-Za-z0-9_.\-]+", "_", s).strip("_")
    return s[:48] if s else "EMPTY"


def render_edges(sealer: EntitySeal, edges, passthrough_num=True):
    lines = []
    for h, r, t in edges:
        if passthrough_num and str(t).startswith("NUM_"):
            lines.append(f"{sealer.atom(h)} | {sealer.atom(r)} | {t[4:]}")
        else:
            lines.append(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}")
    return "\n".join(lines)


def write_batch(name, header, items):
    d = RUNS / f"{name}_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "Context from real FinQA / WikiTableQuestions tables, sealed.\n",
        "Same encoding on question and context. No external world knowledge.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>  OR  ANSWER_NUM[<id>]: <number> when instructed.\n",
        "FinQA items use ANSWER_NUM (computed). WTQ items use ANSWER_SEALED (cell copy).\n",
        header + "\n",
    ]
    for cid, body in items:
        lines.append(f"\n##### ID {cid} #####\n{body}\n")
    (d / "BATCH.txt").write_text("\n".join(lines))
    return str(d / "BATCH.txt")


def build_finqa_suite(examples, sealer: EntitySeal):
    """NL vs gold-program; numbers stay plaintext (arithmetic); labels sealed.
    Full numeric sealing makes operators meaningless — documented in BENCHMARKS.md.
    """
    nl_items, prog_items = [], []
    cases = []
    sheets = {}
    for i, ex in enumerate(examples):
        edges, _ = table_to_kv_edges(ex["table"], seal_numbers=False)
        ctx = render_edges(sealer, edges, passthrough_num=True)
        # Seal question text but keep digits in question as-is for fairness with NUM answers
        q_sealed = sealer.text(re.sub(r"(\d)", r" \1 ", ex["question"]))  # weak; prefer full seal of words
        q_sealed = "".join(
            (p if re.fullmatch(r"\d+\.?\d*", p) else sealer.atom(p) if re.fullmatch(r"[A-Za-z0-9_.\-]+", p) else p)
            for p in re.findall(r"[A-Za-z0-9_.\-]+|[^A-Za-z0-9_.\-]+", ex["question"])
        )
        prog_plain = ex["program"]  # keep operators + numbers plaintext
        prog_block = (
            "FINQA_PROGRAM (operators+numbers plaintext; CONTEXT row/col labels sealed)\n"
            f"{prog_plain}\n"
            "Execute over CONTEXT. Return numeric result."
        )
        cid_n = f"FQ_NL_{i}"
        cid_p = f"FQ_PROG_{i}"
        nl_items.append(
            (
                cid_n,
                f"STRATUM: {ex['stratum']} depth={ex['depth']}\nSOURCE: FinQA {ex['id']}\n"
                f"QUESTION:\n{q_sealed}\n\nCONTEXT:\n{ctx}\n\n"
                f"Reply: ANSWER_NUM[{cid_n}]: <number>",
            )
        )
        prog_items.append(
            (
                cid_p,
                f"STRATUM: {ex['stratum']} depth={ex['depth']}\nSOURCE: FinQA {ex['id']}\n"
                f"{prog_block}\n\nCONTEXT:\n{ctx}\n\n"
                f"Reply: ANSWER_NUM[{cid_p}]: <number>",
            )
        )
        cases.append(
            {
                "id": cid_n,
                "form": "NL",
                "bench": "FinQA",
                "stratum": ex["stratum"],
                "depth": ex["depth"],
                "expect_num": ex["exe_ans"],
                "answer_mode": "NUM",
                "opacity": "labels_sealed_numbers_plain",
                "question": ex["question"],
                "program": ex["program"],
                "src_id": ex["id"],
            }
        )
        cases.append(
            {
                "id": cid_p,
                "form": "PROG",
                "bench": "FinQA",
                "stratum": ex["stratum"],
                "depth": ex["depth"],
                "expect_num": ex["exe_ans"],
                "answer_mode": "NUM",
                "opacity": "labels_sealed_numbers_plain",
                "question": ex["question"],
                "program": ex["program"],
                "src_id": ex["id"],
            }
        )
        sheets[f"FQ_{i}_{ex['stratum'][:8]}"] = ex["table"]
    return nl_items, prog_items, cases, sheets


def build_wtq_suite(examples, sealer: EntitySeal):
    nl_items = []
    cases = []
    sheets = {}
    for i, ex in enumerate(examples):
        with open(ex["table_path"], newline="", encoding="utf-8", errors="replace") as f:
            table = list(csv.reader(f))
        edges, _ = table_to_kv_edges(table, max_rows=20, seal_numbers=True)
        ctx = render_edges(sealer, edges, passthrough_num=False)
        ans_tok = atomize(ex["target"].split("|")[0].strip())
        expect = sealer.atom(ans_tok)
        in_ctx = any(sealer.atom(t) == expect for _, _, t in edges)
        cid = f"WTQ_NL_{i}"
        nl_items.append(
            (
                cid,
                f"STRATUM: {ex['stratum']}\nSOURCE: WikiTableQuestions {ex['id']}\n"
                f"QUESTION:\n{sealer.text(ex['question'])}\n\nCONTEXT:\n{ctx}\n\n"
                f"Reply: ANSWER_SEALED[{cid}]: <seal_or_UNKNOWN>",
            )
        )
        cases.append(
            {
                "id": cid,
                "form": "NL",
                "bench": "WikiTableQuestions",
                "stratum": ex["stratum"],
                "expect": expect,
                "target": ex["target"],
                "answer_in_context": in_ctx,
                "answer_mode": "SEALED",
                "question": ex["question"],
                "src_id": ex["id"],
                "table_path": ex["table_path"],
            }
        )
        sheets[f"WTQ_{i}_{ex['stratum'][:8]}"] = table[:25]
    return nl_items, cases, sheets


def dump_pdf(xlsx_path: Path):
    try:
        from reportlab.pdfgen import canvas as pdfcanvas
        from reportlab.lib.pagesizes import letter
        from openpyxl import load_workbook

        pdf = xlsx_path.with_suffix(".pdf")
        c = pdfcanvas.Canvas(str(pdf), pagesize=letter)
        c.setFont("Helvetica", 8)
        y = 750
        wb = load_workbook(xlsx_path, read_only=True)
        for name in wb.sheetnames[:6]:
            c.drawString(40, y, f"Sheet: {name}")
            y -= 12
            for row in wb[name].iter_rows(values_only=True):
                line = " | ".join("" if x is None else str(x) for x in row)[:100]
                c.drawString(40, y, line)
                y -= 10
                if y < 40:
                    c.showPage()
                    c.setFont("Helvetica", 8)
                    y = 750
            y -= 10
        c.save()
        return pdf
    except Exception as e:
        return None


def main():
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    sealer = EntitySeal(KEY)

    finqa = load_finqa(N_FINQA, rng)
    wtq = load_wtq(N_WTQ, rng)

    fq_nl, fq_prog, fq_cases, fq_sheets = build_finqa_suite(finqa, sealer)
    wtq_nl, wtq_cases, wtq_sheets = build_wtq_suite(wtq, sealer)

    # big excel: many sheets
    big_xlsx = OUT / "complex_finqa_wtq.xlsx"
    write_xlsx(big_xlsx, {**fq_sheets, **wtq_sheets})
    pdf = dump_pdf(big_xlsx)

    # also mega single-sheet dump of OpenData500 full usable for "big excel"
    od = ROOT / "data/real_docs/opendata500_us_companies.csv"
    mega_rows = [["company", "city", "state", "category", "employees", "founded"]]
    with od.open() as f:
        for r in csv.DictReader(f):
            if r.get("company_name") and r.get("city"):
                mega_rows.append(
                    [
                        r["company_name"],
                        r["city"],
                        r.get("state", ""),
                        r.get("company_category", ""),
                        r.get("full_time_employees", ""),
                        r.get("year_founded", ""),
                    ]
                )
    mega_xlsx = OUT / "opendata500_full.xlsx"
    write_xlsx(mega_xlsx, {"Companies": mega_rows})

    paths = {
        "FINQA_NL": write_batch("FINQA_NL", "FinQA sealed NL over financial tables.", fq_nl),
        "FINQA_PROG": write_batch("FINQA_PROG", "FinQA sealed gold PROGRAM over same tables.", fq_prog),
        "WTQ_NL": write_batch("WTQ_NL", "WikiTableQuestions sealed NL over Wikipedia tables.", wtq_nl),
    }

    harness = {
        "n_finqa": len(finqa),
        "n_wtq": len(wtq),
        "strata_finqa": {s: sum(1 for e in finqa if e["stratum"] == s) for s in {e["stratum"] for e in finqa}},
        "strata_wtq": {s: sum(1 for e in wtq if e["stratum"] == s) for s in {e["stratum"] for e in wtq}},
        "workbooks": {
            "complex_xlsx": str(big_xlsx),
            "complex_pdf": str(pdf) if pdf else None,
            "opendata500_full_xlsx": str(mega_xlsx),
            "opendata500_rows": len(mega_rows) - 1,
        },
        "paths": paths,
        "cases": fq_cases + wtq_cases,
        "rev": sealer.rev,
        "note": "FinQA answers may be computed (not in table); score answer_in_context separately. PROG uses gold FinQA programs sealed.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "complex_bench_harness.json").write_text(json.dumps(harness, indent=2))
    print(
        json.dumps(
            {
                "finqa": harness["n_finqa"],
                "wtq": harness["n_wtq"],
                "strata_finqa": harness["strata_finqa"],
                "strata_wtq": harness["strata_wtq"],
                "xlsx": str(big_xlsx),
                "mega_rows": harness["workbooks"]["opendata500_rows"],
                "pdf": harness["workbooks"]["complex_pdf"],
                "batches": list(paths.keys()),
                "finqa_answer_in_ctx": sum(1 for c in fq_cases if c["form"] == "NL" and c.get("answer_in_context")),
                "finqa_mode": "ANSWER_NUM",
                "wtq_in_ctx": sum(1 for c in wtq_cases if c.get("answer_in_context")),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
