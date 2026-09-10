#!/usr/bin/env python3
"""Score compiler-stack replies + SealRouter symbolic upper bound."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from seal_router import SealRouter  # noqa: E402

RESULTS = ROOT / "results"
HARNESS = json.loads((RESULTS / "compiler_stack_harness.json").read_text())


def parse_answers(text: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", text):
        out[m.group(1)] = m.group(2).strip()
    return out


def parse_mids(text: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"MID_SEALED\[([^\]]+)\]:\s*(\S+)", text):
        out[m.group(1)] = m.group(2).strip()
    return out


def score_condition(cond: str, answers: dict[str, str], mids: dict[str, str] | None = None):
    rows = [c for c in HARNESS["cases"] if c["cond"] == cond]
    correct = 0
    company_stops = 0
    detail = []
    for c in rows:
        pred = answers.get(c["id"], "MISSING")
        ok = pred == c["expect"]
        if ok:
            correct += 1
        stop = False
        if "intermediate_company" in c and pred == c["intermediate_company"]:
            company_stops += 1
            stop = True
        mid_ok = None
        if mids is not None and "expect_mid" in c:
            mid_ok = mids.get(c["id"]) == c["expect_mid"]
        detail.append(
            {
                "id": c["id"],
                "ok": ok,
                "pred": pred,
                "expect": c["expect"],
                "company_stop": stop,
                "mid_ok": mid_ok,
                "person": c.get("person"),
                "plain_hq": c.get("plain_hq"),
            }
        )
    return {
        "cond": cond,
        "score": f"{correct}/{len(rows)}",
        "n_correct": correct,
        "n": len(rows),
        "company_stops": company_stops,
        "detail": detail,
    }


def sealrouter_bound():
    """Parse COMP/TWIN batches and verify symbolic path execution."""
    from pathlib import Path as P

    runs = {
        "compiled_path": P(ROOT / "runs/compiler_comp_ONLY/BATCH.txt"),
        "compiled_twin": P(ROOT / "runs/compiler_twin_ONLY/BATCH.txt"),
    }
    bound = {}
    for cond, path in runs.items():
        text = path.read_text()
        blocks = re.split(r"##### ID (CMP_\w+) #####", text)[1:]
        ok_n = 0
        n = 0
        for i in range(0, len(blocks), 2):
            cid, body = blocks[i], blocks[i + 1]
            start_m = re.search(r"START (E[0-9a-f]+)", body)
            r1_m = re.search(r"R1 (E[0-9a-f]+)", body)
            r2_m = re.search(r"R2 (E[0-9a-f]+)", body)
            triples = re.findall(r"(E[0-9a-f]+)\s*\|\s*(E[0-9a-f]+)\s*\|\s*(E[0-9a-f]+)", body)
            case = next(c for c in HARNESS["cases"] if c["id"] == cid)
            router = SealRouter([(h, r, t) for h, r, t in triples])
            outs = router.path(start_m.group(1), [r1_m.group(1), r2_m.group(1)])
            uniq = list(dict.fromkeys(outs))
            n += 1
            if uniq == [case["expect"]]:
                ok_n += 1
        bound[cond] = f"{ok_n}/{n}"
    return bound


def main():
    reply_dir = RESULTS / "compiler_replies"
    reply_dir.mkdir(parents=True, exist_ok=True)

    # If CLI args are reply files: score_compiler.py raw.txt comp.txt twin.txt probe.txt
    files = {
        "raw_sealed_nl": reply_dir / "raw.txt",
        "compiled_path": reply_dir / "comp.txt",
        "compiled_twin": reply_dir / "twin.txt",
        "probe_mid_final": reply_dir / "probe.txt",
    }
    if len(sys.argv) >= 5:
        files = {
            "raw_sealed_nl": Path(sys.argv[1]),
            "compiled_path": Path(sys.argv[2]),
            "compiled_twin": Path(sys.argv[3]),
            "probe_mid_final": Path(sys.argv[4]),
        }

    report = {
        "compiler_selftest": HARNESS["compiler_selftest"],
        "sealrouter_bound": sealrouter_bound(),
        "models": {},
    }

    # model tagged filenames: raw_composer.txt etc.
    for cond, path in files.items():
        if not path.exists():
            # try model-tagged
            alts = list(reply_dir.glob(f"{path.stem}_*.txt"))
            if not alts:
                report[cond] = {"status": "missing", "path": str(path)}
                continue
            for alt in alts:
                model = alt.stem.split("_", 1)[-1]
                text = alt.read_text()
                answers = parse_answers(text)
                mids = parse_mids(text) if cond == "probe_mid_final" else None
                sc = score_condition(cond, answers, mids)
                report.setdefault("models", {}).setdefault(model, {})[cond] = sc
            continue
        text = path.read_text()
        answers = parse_answers(text)
        mids = parse_mids(text) if cond == "probe_mid_final" else None
        report[cond] = score_condition(cond, answers, mids)

    (RESULTS / "compiler_stack_results.json").write_text(json.dumps(report, indent=2))
    # compact summary
    summary = {"sealrouter_bound": report["sealrouter_bound"], "compiler_selftest": report["compiler_selftest"]}
    for k, v in report.items():
        if isinstance(v, dict) and "score" in v:
            summary[k] = {
                "score": v["score"],
                "company_stops": v.get("company_stops"),
            }
    if report.get("models"):
        for m, conds in report["models"].items():
            summary[m] = {c: {"score": s["score"], "company_stops": s.get("company_stops")} for c, s in conds.items()}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
