#!/usr/bin/env python3
"""Score complex FinQA/WTQ sealed batches."""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "complex_bench_harness.json").read_text())
REPLY = RESULTS / "complex_replies"


def parse_sealed(text):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", text)}


def parse_num(text):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"ANSWER_NUM\[([^\]]+)\]:\s*(\S+)", text)}


def close_num(a, b, tol=1e-2):
    try:
        fa, fb = float(str(a).replace(",", "")), float(str(b).replace(",", ""))
        if fb == 0:
            return fa == 0
        return abs(fa - fb) / max(abs(fb), 1e-9) < tol or abs(fa - fb) < tol
    except Exception:
        return str(a).strip() == str(b).strip()


def main():
    REPLY.mkdir(parents=True, exist_ok=True)
    report = {"by_batch": {}, "by_stratum": {}}
    files = {
        "FINQA_NL": ("NL", "FinQA", "NUM"),
        "FINQA_PROG": ("PROG", "FinQA", "NUM"),
        "WTQ_NL": ("NL", "WikiTableQuestions", "SEALED"),
    }
    for key, (form, bench, mode) in files.items():
        p = REPLY / f"{key}_composer.txt"
        if not p.exists():
            report["by_batch"][key] = {"status": "pending"}
            continue
        text = p.read_text()
        rows = [c for c in H["cases"] if c["form"] == form and c["bench"] == bench]
        ok = 0
        detail = []
        if mode == "NUM":
            preds = parse_num(text)
            for c in rows:
                pred = preds.get(c["id"], "MISSING")
                hit = close_num(pred, c["expect_num"])
                ok += int(hit)
                detail.append({"id": c["id"], "ok": hit, "pred": pred, "expect": c["expect_num"], "stratum": c["stratum"]})
        else:
            preds = parse_sealed(text)
            for c in rows:
                pred = preds.get(c["id"], "MISSING")
                hit = pred == c["expect"]
                ok += int(hit)
                detail.append({"id": c["id"], "ok": hit, "pred": pred, "expect": c["expect"], "stratum": c["stratum"], "in_ctx": c.get("answer_in_context")})
        report["by_batch"][key] = {"score": f"{ok}/{len(rows)}", "n": len(rows), "detail": detail}
        for d in detail:
            s = d["stratum"]
            report["by_stratum"].setdefault(f"{key}:{s}", {"ok": 0, "n": 0})
            report["by_stratum"][f"{key}:{s}"]["n"] += 1
            report["by_stratum"][f"{key}:{s}"]["ok"] += int(d["ok"])
    for k, v in list(report["by_stratum"].items()):
        report["by_stratum"][k] = f"{v['ok']}/{v['n']}"
    (RESULTS / "complex_bench_results.json").write_text(json.dumps(report, indent=2))
    slim = {k: {kk: vv for kk, vv in v.items() if kk != "detail"} if isinstance(v, dict) else v for k, v in report["by_batch"].items()}
    print(json.dumps({"by_batch": slim, "by_stratum": report["by_stratum"]}, indent=2))


if __name__ == "__main__":
    main()
