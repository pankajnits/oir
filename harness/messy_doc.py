#!/usr/bin/env python3
"""Messy-doc sealed IR: incident-prose dump (PDF-extract style), competing advice.

Not a vendor PDF parser bake-off. Context is unstructured pages with boilerplate,
timestamps, and two Recommended_action lines (gold on start ID, trap on distractor).

  NL       — sealed Q, no extractive rule (authoring floor)
  EXTRACT  — sealed Q; copy recommended_action from the note that names START

Isolation, per-item HMAC, n=6. Seals ≠ confidentiality. Not medical/legal advice.
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

from oir import EntitySeal
from grev1_fullq_prog import seal_question
from wilson_cis import wilson
from future_unlock import worlds

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "messy_doc"
SEED = 20260818
N = 6


def messy_pages(w, sealer: EntitySeal) -> str:
    s, g, t = w["start"], w["gold_a"], w["trap_a"]
    dx = f"{s}_X"
    sS, gS, tS, dS = sealer.atom(s), sealer.atom(g), sealer.atom(t), sealer.atom(dx)
    return "\n".join(
        [
            "=== PDF EXTRACT page 1/3 ===",
            "CONFIDENTIAL — auto-OCR from incident.pdf",
            "Generated: 2026-08-17T13:00:00Z  ticket-export",
            "Header: please ignore banners, routing codes, and footer hashes.",
            "",
            f"Subject: follow-up on {sS}",
            f"Body: {sS} is in the active set. Notes from the on-call paste:",
            f"{sS} status=open. recommended_action {gS}. Do not {tS}.",
            "=== PDF EXTRACT page 2/3 ===",
            "Appendix A — related but different ID (do not mix).",
            f"{dS} is a closed nuisance thread. recommended_action {tS}.",
            "Footer: page 2 of 3  confidential  do not forward",
            "=== PDF EXTRACT page 3/3 ===",
            "Boilerplate SLA text. No recommended_action on this page.",
            f"Index mentions {sS} and {dS} without a decision.",
        ]
    )


def pack(cid: str, header: str, q: str, ctx: str) -> str:
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
            "CONTEXT (PDF extract, sealed):",
            ctx,
            "",
        ]
    )


def build():
    rng = random.Random(SEED)
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)
    cases = []
    for i in range(N):
        w = worlds(i)
        sealer = EntitySeal(rng.randbytes(16))
        start = sealer.atom(w["start"])
        gold = sealer.atom(w["gold_a"])
        trap = sealer.atom(w["trap_a"])
        ctx = messy_pages(w, sealer)
        q_nl = seal_question(f"What should we do for {start}?", sealer, {start})
        q_ex = f"Return recommended_action for {start} from the note that names that id."
        for arm, q, header in (
            (
                "NL",
                q_nl,
                "ARM NL: messy PDF extract, sealed. No extractive rule. If ambiguous, UNKNOWN.",
            ),
            (
                "EXTRACT",
                q_ex,
                "ARM EXTRACT: messy PDF extract. IDs and actions sealed; predicate recommended_action is readable. Copy that token from the note that names START.",
            ),
        ):
            cid = f"MESSY_{arm}_{i}"
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, header, q, ctx))
            leaked = w["gold_a"] in path.read_text() or w["trap_a"] in path.read_text()
            cases.append(
                {
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "kind": w["kind"],
                    "gold": gold,
                    "trap": trap,
                    "start": start,
                    "start_in_q": start in q,
                    "plaintext_action_in_prompt": leaked,
                    "path": str(path),
                    "iso": True,
                    "per_item_key": True,
                }
            )
    h = {
        "n": N,
        "suite": "messy_doc",
        "seed": SEED,
        "nonclaim": "PDF-extract *style* prose, not vendor OCR. Predicate recommended_action left readable (schema). IDs/actions sealed. v1 full-HMAC EXTRACT 0/6 was a case/predicate confound.",
        "cases": cases,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "messy_doc_harness.json"
    out.write_text(json.dumps(h, indent=2))
    print(json.dumps({
        "n": N,
        "leaks": sum(c["plaintext_action_in_prompt"] for c in cases),
        "start_in_q": sum(c["start_in_q"] for c in cases),
        "out": str(out),
    }, indent=2))


def score(model: str):
    H = json.loads((RESULTS / "messy_doc_harness.json").read_text())
    SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
    preds = {}
    d = RESULTS / f"messy_doc_replies_{model}"
    if d.exists():
        for p in d.rglob("*.txt"):
            text = p.read_text()
            tagged = list(SEAL.finditer(text))
            for m in tagged:
                preds[m.group(1)] = m.group(2).strip()
            if not tagged and re.search(r"\bUNKNOWN\b", text, re.I):
                mm = re.search(r"MESSY_(?:NL|EXTRACT)_\d+", text)
                if mm:
                    preds[mm.group(0)] = "UNKNOWN"
    rows = []
    for c in H["cases"]:
        pred = preds.get(c["id"], "MISSING")
        if pred == c["gold"]:
            kind = "gold"
        elif pred.upper() == "UNKNOWN":
            kind = "unknown"
        elif pred == c["trap"]:
            kind = "trap"
        elif pred == "MISSING":
            kind = "missing"
        else:
            kind = "other"
        rows.append({**{k: v for k, v in c.items() if k != "path"}, "pred": pred, "kind": kind, "ok": kind == "gold"})

    def arm_sum(arm):
        rs = [r for r in rows if r["arm"] == arm]
        missing = sum(1 for r in rs if r["kind"] == "missing")
        scored = [r for r in rs if r["kind"] != "missing"]
        n = len(scored)
        g = sum(1 for r in scored if r["kind"] == "gold")
        if not scored and missing:
            return {
                "score": "not_run",
                "wilson": None,
                "gold": 0,
                "trap": 0,
                "unknown": 0,
                "missing": missing,
            }
        return {
            "score": f"{g}/{n}" if n else "0/0",
            "wilson": wilson(g, n) if n else None,
            "gold": g,
            "trap": sum(1 for r in scored if r["kind"] == "trap"),
            "unknown": sum(1 for r in scored if r["kind"] == "unknown"),
            "missing": missing,
        }

    summary = {"NL": arm_sum("NL"), "EXTRACT": arm_sum("EXTRACT")}
    path = RESULTS / f"messy_doc_{model}.json"
    path.write_text(json.dumps({"model": model, "n": H["n"], "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else "gpt56")
    else:
        build()
