#!/usr/bin/env python3
"""Score adversarial opaque induction."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLIES = RESULTS / "adv_induction_replies"
HARNESS = RESULTS / "adv_induction_harness.json"
ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def load_preds(arm: str) -> dict[str, str]:
    preds: dict[str, str] = {}
    d = REPLIES / arm
    if d.is_dir():
        for p in sorted(d.glob("item_*.txt")):
            preds.update({m.group(1): m.group(2) for m in ANS_RE.finditer(p.read_text())})
    agg = REPLIES / f"{arm}_composer.txt"
    if agg.exists():
        preds.update({m.group(1): m.group(2) for m in ANS_RE.finditer(agg.read_text())})
    return preds


def main():
    h = json.loads(HARNESS.read_text())
    golds = {c["id"]: c for c in h["cases"]}
    summary = {}
    rows = []
    for arm, meta in h["arms"].items():
        preds = load_preds(arm)
        oks = []
        trap_hits = []
        wrong2 = []
        for cid in meta["ids"]:
            c = golds[cid]
            gold = c["gold"]
            pred = preds.get(cid, "")
            ok = pred == gold
            oks.append(ok)
            th = bool(c.get("trap")) and pred == c["trap"]
            w2 = bool(c.get("wrong_2hop")) and pred == c["wrong_2hop"]
            trap_hits.append(th)
            wrong2.append(w2)
            rows.append(
                {
                    "arm": arm,
                    "id": cid,
                    "gold": gold,
                    "pred": pred,
                    "ok": ok,
                    "chose_trap": th,
                    "chose_wrong_2hop": w2,
                    "unknown": pred.upper() == "UNKNOWN",
                }
            )
        summary[arm] = {
            "score": f"{sum(oks)}/{len(oks)}",
            "trap_rate": f"{sum(trap_hits)}/{len(trap_hits)}",
            "wrong2_rate": f"{sum(wrong2)}/{len(wrong2)}",
            "unknown": sum(1 for cid in meta["ids"] if preds.get(cid, "").upper() == "UNKNOWN"),
        }
    out = {
        "summary": summary,
        "rows": rows,
        "verdict": (
            f"SAME_TRAP={summary.get('SAME_TRAP',{}).get('score')}; "
            f"CROSS_TRAP={summary.get('CROSS_TRAP',{}).get('score')} "
            f"(trap_rate={summary.get('CROSS_TRAP',{}).get('trap_rate')}); "
            f"SAME_BAL={summary.get('SAME_BALANCED',{}).get('score')}; "
            f"CROSS_BAL={summary.get('CROSS_BALANCED',{}).get('score')}; "
            f"HOP_MISMATCH={summary.get('HOP_MISMATCH',{}).get('score')} "
            f"(wrong2={summary.get('HOP_MISMATCH',{}).get('wrong2_rate')}); "
            f"PATH={summary.get('PATH_TRAP',{}).get('score')}."
        ),
    }
    (RESULTS / "adv_induction_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(out["verdict"])


if __name__ == "__main__":
    main()
