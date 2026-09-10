#!/usr/bin/env python3
"""Score real-complex long verify (FinQA NUM + WTQ seals)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLY = RESULTS / "real_complex_verify_replies"
H = json.loads((RESULTS / "real_complex_verify_harness.json").read_text())


def parse_num(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"ANSWER_NUM\[([^\]]+)\]:\s*([^\n]+)", text, flags=re.I)
    }


def parse_seal(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", text, flags=re.I)
    }


def num_ok(pred: str, expect) -> bool:
    try:
        p = float(re.sub(r"[^\d.eE+-]", "", pred.split()[0]))
        e = float(expect)
        if e == 0:
            return abs(p) < 1e-4
        return abs(p - e) / max(abs(e), 1e-9) < 0.02 or abs(p - e) < 0.05
    except Exception:
        return False


def main():
    by = defaultdict(lambda: {"ok": 0, "n": 0, "detail": []})
    for form in ["FQ_NL", "FQ_PROG", "FQ_FOLLOW", "WTQ_NL", "WTQ_DSL"]:
        paths = [REPLY / f"{form}_composer.txt", REPLY / f"{form}.txt"]
        text = next((p.read_text() for p in paths if p.exists()), "")
        if not text:
            print("MISSING", form)
            continue
        nums, seals = parse_num(text), parse_seal(text)
        for c in H["cases"]:
            if c["form"] != form:
                continue
            if form.startswith("FQ"):
                pred = nums.get(c["id"], "MISSING")
                ok = num_ok(pred, c["expect_num"])
                by[form]["detail"].append(
                    {"id": c["id"], "ok": ok, "pred": pred, "expect": c["expect_num"], "depth": c.get("depth"), "q": c.get("question", "")[:80]}
                )
            else:
                pred = seals.get(c["id"], "MISSING")
                ok = pred == c["expect"]
                by[form]["detail"].append(
                    {"id": c["id"], "ok": ok, "pred": pred, "expect": c["expect"], "stratum": c.get("stratum"), "q": c.get("question", "")[:80]}
                )
            by[form]["n"] += 1
            by[form]["ok"] += int(ok)
        by[form]["score"] = f"{by[form]['ok']}/{by[form]['n']}"
    out = {
        "context_tokens_est": H.get("context_tokens_est"),
        "n_tables": H.get("n_tables"),
        "summary": {k: v.get("score") for k, v in by.items()},
        "by_form": dict(by),
        "claim": H.get("claim"),
    }
    (RESULTS / "real_complex_verify_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({"tokens": out["context_tokens_est"], "tables": out["n_tables"], "summary": out["summary"]}, indent=2))


if __name__ == "__main__":
    main()
