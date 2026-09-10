#!/usr/bin/env python3
"""Score adv_induction from model-tagged reply root."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HARNESS = RESULTS / "adv_induction_harness.json"
ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else ""
    replies = RESULTS / (f"adv_induction_replies_{model}" if model else "adv_induction_replies")
    h = json.loads(HARNESS.read_text())
    golds = {c["id"]: c for c in h["cases"]}
    summary, rows = {}, []
    for arm, meta in h["arms"].items():
        preds: dict[str, str] = {}
        d = replies / arm
        if d.is_dir():
            for p in sorted(d.glob("item_*.txt")):
                preds.update({m.group(1): m.group(2) for m in ANS_RE.finditer(p.read_text())})
        oks, traps = [], []
        for cid in meta["ids"]:
            c = golds[cid]
            pred = preds.get(cid, "")
            ok = pred == c["gold"]
            th = bool(c.get("trap")) and pred == c["trap"]
            oks.append(ok)
            traps.append(th)
            rows.append({"arm": arm, "id": cid, "gold": c["gold"], "pred": pred, "ok": ok, "chose_trap": th})
        summary[arm] = {
            "score": f"{sum(oks)}/{len(oks)}" if oks else "0/0",
            "trap_rate": f"{sum(traps)}/{len(traps)}" if traps else "0/0",
            "unknown": sum(1 for cid in meta["ids"] if preds.get(cid, "").upper() == "UNKNOWN"),
            "missing": sum(1 for cid in meta["ids"] if cid not in preds),
        }
    out = {"model": model or "composer", "summary": summary, "rows": rows, "reply_dir": str(replies)}
    path = RESULTS / (f"adv_induction_results_{model}.json" if model else "adv_induction_results.json")
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
