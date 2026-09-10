#!/usr/bin/env python3
"""Score use_case_complex from results/cx_replies_<model>/."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "use_case_complex_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(\S+)", re.I)
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
NUM = re.compile(r"ANSWER_NUM\[([^\]]+)\]:\s*(\S+)", re.I)

ARMS = [
    ("CX3_PLAIN_PROG", "plain", "expect_plain", "CX3_PLAIN_{i}"),
    ("CX3_SEAL_PROG", "seal", "expect_seal", "CX3_SEALPROG_{i}"),
    ("CX3_SEAL_NL", "seal", "expect_seal", "CX3_SEALNL_{i}"),
    ("CX3_SEAL_BOTH", "seal", "expect_seal", "CX3_SEALBOTH_{i}"),
    ("COUNT_PROG", "num", "expect_count", "CXCOUNT_PROG_{i}"),
    ("COUNT_NL", "num", "expect_count", "CXCOUNT_NL_{i}"),
    ("SUBJ_PROG", "seal", "expect_action_seal", "CXSUBJ_PROG_{i}"),
    ("SUBJ_NL", "seal", "expect_action_seal", "CXSUBJ_NL_{i}"),
]


def parse(path: Path, kind: str) -> dict[str, str]:
    if not path.exists():
        return {}
    rx = {"plain": PLAIN, "seal": SEAL, "num": NUM}[kind]
    return {m.group(1): m.group(2) for m in rx.finditer(path.read_text())}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    reply = RESULTS / f"cx_replies_{model}"
    cases = H["cases"]
    n = len(cases)
    summary, rows = {}, []
    for arm, kind, gold_key, idpat in ARMS:
        preds = parse(reply / f"{arm}.txt", kind)
        oks = []
        for c in cases:
            cid = idpat.format(i=c["i"])
            gold = str(c[gold_key])
            pred = preds.get(cid, "MISSING")
            ok = pred == gold
            # subjective NL: allow gold token to appear inside a longer answer
            if arm == "SUBJ_NL" and pred != "MISSING" and gold in pred:
                ok = True
            oks.append(ok)
            rows.append({"arm": arm, "id": cid, "use": c["use"], "gold": gold, "pred": pred, "ok": ok})
        summary[arm] = {"score": f"{sum(oks)}/{n}", "missing": sum(1 for x in rows[-n:] if x["pred"] == "MISSING")}
    out = {"model": model, "n": n, "summary": summary, "rows": rows, "reply_dir": str(reply)}
    path = RESULTS / f"use_case_complex_{model}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
