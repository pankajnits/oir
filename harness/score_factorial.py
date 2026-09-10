#!/usr/bin/env python3
"""Score SEAL-Bench-Real factorial replies → paper Table 1 JSON."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HARNESS = json.loads((RESULTS / "seal_bench_real_factorial_harness.json").read_text())
REPLY = RESULTS / "factorial_replies"


def parse_answers(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", text)}


def parse_mids(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"MID_SEALED\[([^\]]+)\]:\s*(\S+)", text)}


def score_form(form: str, answers: dict[str, str], mids: dict[str, str] | None = None):
    rows = [c for c in HARNESS["cases"] if c["form"] == form]
    correct = company_stops = unk = 0
    detail = []
    for c in rows:
        pred = answers.get(c["id"], "MISSING")
        ok = pred == c["expect"]
        if ok:
            correct += 1
        stop = pred == c.get("intermediate_company")
        if stop:
            company_stops += 1
        if pred == "UNKNOWN":
            unk += 1
        mid_ok = None
        if mids is not None and "expect_mid" in c:
            mid_ok = mids.get(c["id"]) == c["expect_mid"]
        twin_flip = None
        if form == "PROG_TWIN" and "original_expect" in c:
            twin_flip = ok and pred != c["original_expect"]
        detail.append(
            {
                "id": c["id"],
                "ok": ok,
                "pred": pred,
                "expect": c["expect"],
                "company_stop": stop,
                "mid_ok": mid_ok,
                "twin_flip": twin_flip,
                "person": c.get("person"),
            }
        )
    twin_flips = sum(1 for d in detail if d["twin_flip"]) if form == "PROG_TWIN" else None
    mid_correct = None
    if mids is not None:
        mid_correct = sum(1 for d in detail if d["mid_ok"])
    return {
        "form": form,
        "score": f"{correct}/{len(rows)}",
        "n_correct": correct,
        "n": len(rows),
        "company_stops": company_stops,
        "unknown": unk,
        "twin_flips": f"{twin_flips}/{len(rows)}" if twin_flips is not None else None,
        "mid_correct": f"{mid_correct}/{len(rows)}" if mid_correct is not None else None,
        "detail": detail,
    }


def main():
    REPLY.mkdir(parents=True, exist_ok=True)
    report = {
        "bench": HARNESS["bench"],
        "n_quiz": HARNESS["n_quiz"],
        "router_bound": HARNESS["router_bound"],
        "table1": {},
        "models": {},
    }
    # expect files: NL_composer.txt etc. or NL.txt
    for form in HARNESS["forms"]:
        candidates = []
        for p in [
            REPLY / f"{form}_composer.txt",
            REPLY / f"{form}_claude.txt",
            REPLY / f"{form}.txt",
        ]:
            if p.exists():
                candidates.append(p)
        if not candidates:
            report["table1"][form] = {"status": "pending"}
            continue
        for path in candidates:
            text = path.read_text()
            stem = path.stem
            if stem.endswith("_claude"):
                model = "claude"
                form_key = stem[: -len("_claude")]
            elif stem.endswith("_composer"):
                model = "composer"
                form_key = stem[: -len("_composer")]
            elif "_" in stem:
                form_key, model = stem.split("_", 1)
            else:
                form_key, model = stem, "composer"
            # allow filename form alias
            if form_key != form and form_key.upper() != form:
                # file may be named exactly as form with model suffix already stripped
                pass
            mids = parse_mids(text) if form == "SCAFFOLD" else None
            sc = score_form(form, parse_answers(text), mids)
            report["models"].setdefault(model, {})[form] = sc
            if model == "composer":
                report["table1"][form] = {
                    "score": sc["score"],
                    "company_stops": sc["company_stops"],
                    "unknown": sc["unknown"],
                    "twin_flips": sc["twin_flips"],
                    "mid_correct": sc["mid_correct"],
                }

    out = RESULTS / "seal_bench_real_factorial_results.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"table1": report["table1"], "router_bound": report["router_bound"]}, indent=2))


if __name__ == "__main__":
    main()
