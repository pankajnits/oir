#!/usr/bin/env python3
"""Score adv_induction_n24 from results/adv_n24_replies_<model>/."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "adv_induction_n24_harness.json").read_text())
ANS = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def load_preds(reply: Path, arm: str) -> dict[str, str]:
    preds: dict[str, str] = {}
    for name in (f"{arm}.txt", f"{arm}_ONLY.txt", "BATCH.txt"):
        p = reply / name
        if p.exists():
            preds.update({m.group(1): m.group(2) for m in ANS.finditer(p.read_text())})
    d = reply / arm
    if d.is_dir():
        for p in d.glob("item_*.txt"):
            preds.update({m.group(1): m.group(2) for m in ANS.finditer(p.read_text())})
    return preds


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    reply = RESULTS / f"adv_n24_replies_{model}"
    golds = {c["id"]: c for c in H["cases"]}
    summary, rows = {}, []
    for arm, meta in H["arms"].items():
        preds = load_preds(reply, arm)
        oks, traps, unk, miss = [], [], 0, 0
        for cid in meta["ids"]:
            c = golds[cid]
            pred = preds.get(cid, "")
            if not pred:
                miss += 1
            if pred.upper() == "UNKNOWN":
                unk += 1
            ok = pred == c["gold"]
            th = bool(c.get("trap")) and pred == c["trap"]
            oks.append(ok)
            traps.append(th)
            rows.append({"arm": arm, "id": cid, "gold": c["gold"], "pred": pred or "MISSING", "ok": ok, "chose_trap": th})
        n = len(meta["ids"])
        summary[arm] = {
            "score": f"{sum(oks)}/{n}",
            "trap_rate": f"{sum(traps)}/{n}",
            "unknown": unk,
            "missing": miss,
        }
    out = {"model": model, "n": H["n"], "summary": summary, "rows": rows, "reply_dir": str(reply)}
    path = RESULTS / f"adv_induction_n24_{model}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
