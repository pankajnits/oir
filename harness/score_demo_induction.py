#!/usr/bin/env python3
"""Score demo-only induction arms (v2: one-quiz-per-file replies)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLIES = RESULTS / "demo_induction_replies"
HARNESS = RESULTS / "demo_induction_harness.json"
ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)

ARMS = [f"DEMO_{k}" for k in (0, 1, 2, 4, 8)] + ["LEGEND", "PATH"]


def load_preds_arm(arm: str) -> dict[str, str]:
    """Load from arm aggregate file and/or per-item files."""
    preds: dict[str, str] = {}
    agg = REPLIES / f"{arm}_composer.txt"
    if agg.exists():
        preds.update({m.group(1): m.group(2) for m in ANS_RE.finditer(agg.read_text())})
    arm_dir = REPLIES / arm
    if arm_dir.is_dir():
        for p in sorted(arm_dir.glob("item_*.txt")):
            preds.update({m.group(1): m.group(2) for m in ANS_RE.finditer(p.read_text())})
    return preds


def main():
    h = json.loads(HARNESS.read_text())
    golds = {c["i"]: c["gold"] for c in h["cases"]}
    summary = {}
    rows = []

    for arm in ARMS:
        preds = load_preds_arm(arm)
        oks = []
        for i, gold in golds.items():
            if arm.startswith("DEMO_"):
                k = arm.split("_")[1]
                cid = f"DI_DEMO{k}_{i}"
            elif arm == "LEGEND":
                cid = f"DI_LEGEND_{i}"
            else:
                cid = f"DI_PATH_{i}"
            pred = preds.get(cid, "")
            ok = pred == gold
            oks.append(ok)
            rows.append(
                {
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "gold": gold,
                    "pred": pred,
                    "ok": ok,
                    "unknown": pred.upper() == "UNKNOWN",
                }
            )
        summary[arm] = f"{sum(oks)}/{len(oks)}" if oks else "0/0"

    out = {
        "version": h.get("version", 1),
        "summary": summary,
        "demo_curve": {k: summary[f"DEMO_{k}"] for k in (0, 1, 2, 4, 8)},
        "rows": rows,
        "protocol": h.get("protocol"),
        "v1_discard": h.get("v1_discard"),
        "verdict": (
            "v2 curve (one-quiz-per-file; no English two-hop on DEMO). "
            f"PATH={summary.get('PATH')}; LEGEND={summary.get('LEGEND')}; "
            f"DEMO_0={summary.get('DEMO_0')}."
        ),
    }
    (RESULTS / "demo_induction_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(out["verdict"])


if __name__ == "__main__":
    main()
