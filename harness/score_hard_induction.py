#!/usr/bin/env python3
"""Score hard opaque induction (DEPTH + CROSS)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLIES = RESULTS / "hard_induction_replies"
HARNESS = RESULTS / "hard_induction_harness.json"
ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def load_preds(arm: str) -> dict[str, str]:
    preds: dict[str, str] = {}
    agg = REPLIES / f"{arm}_composer.txt"
    if agg.exists():
        preds.update({m.group(1): m.group(2) for m in ANS_RE.finditer(agg.read_text())})
    d = REPLIES / arm
    if d.is_dir():
        for p in sorted(d.glob("item_*.txt")):
            preds.update({m.group(1): m.group(2) for m in ANS_RE.finditer(p.read_text())})
    return preds


def main():
    h = json.loads(HARNESS.read_text())
    # gold map by id
    golds: dict[str, str] = {}
    for c in h["cases"]:
        if "id" in c:
            golds[c["id"]] = c["gold"]
        elif "id_template" in c:
            # fill demo k variants later from arms
            pass

    # rebuild golds from arms ids + cases
    # DEPTH DEMO golds: from cases with id_template
    depth_quiz_gold: dict[tuple[int, int], str] = {}
    for c in h["cases"]:
        if c.get("suite") == "DEPTH" and "id_template" in c:
            depth_quiz_gold[(c["hop"], c["i"])] = c["gold"]
        if "id" in c and "gold" in c:
            golds[c["id"]] = c["gold"]

    summary = {}
    rows = []
    for arm, meta in h["arms"].items():
        preds = load_preds(arm)
        oks = []
        for i, cid in enumerate(meta["ids"]):
            if cid in golds:
                gold = golds[cid]
            elif meta.get("suite") == "DEPTH" and meta.get("kind") != "PATH":
                hop = meta["hop"]
                gold = depth_quiz_gold[(hop, i)]
            else:
                gold = golds.get(cid, "")
            pred = preds.get(cid, "")
            ok = bool(gold) and pred == gold
            oks.append(ok)
            rows.append(
                {
                    "arm": arm,
                    "id": cid,
                    "gold": gold,
                    "pred": pred,
                    "ok": ok,
                    "unknown": pred.upper() == "UNKNOWN",
                }
            )
        summary[arm] = f"{sum(oks)}/{len(oks)}" if oks else "0/0"

    out = {
        "version": h.get("version"),
        "summary": summary,
        "cross": {
            "CROSS_DEMO_4": summary.get("CROSS_DEMO_4"),
            "SAME_DEMO_4": summary.get("SAME_DEMO_4"),
        },
        "depth": {
            hop: {
                f"DEMO_{k}": summary.get(f"H{hop}_DEMO_{k}")
                for k in (0, 1, 4)
            }
            | {"PATH": summary.get(f"H{hop}_PATH")}
            for hop in (2, 3, 4)
        },
        "rows": rows,
        "verdict": (
            f"CROSS={summary.get('CROSS_DEMO_4')} vs SAME={summary.get('SAME_DEMO_4')}; "
            f"H3_DEMO_4={summary.get('H3_DEMO_4')} H3_PATH={summary.get('H3_PATH')}."
        ),
    }
    (RESULTS / "hard_induction_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(out["verdict"])


if __name__ == "__main__":
    main()
