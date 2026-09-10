#!/usr/bin/env python3
"""Score future_unlock: hops + subjective gold vs trap."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

H = json.loads((ROOT / "results" / "future_unlock_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(.+)$", re.I | re.M)
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ARMS = [
    ("HOP_PLAIN", "plain", "expect_hop_plain"),
    ("HOP_SEAL_PROG", "seal", "expect_hop_seal"),
    ("HOP_SEAL_NL", "seal", "expect_hop_seal"),
    ("SUBJ_NL", "seal", "expect_subj"),
    ("SUBJ_EXTRACT", "seal", "expect_subj"),
]


def parse(path, kind):
    if not path.exists():
        return {}
    rx = PLAIN if kind == "plain" else SEAL
    return {m.group(1): m.group(2).strip() for m in rx.finditer(path.read_text())}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    reply = ROOT / "results" / f"future_unlock_replies_{model}"
    n = H["n"]
    summary, rows = {}, []
    for arm, kind, goldk in ARMS:
        preds = parse(reply / f"{arm}.txt", kind)
        oks, traps = [], []
        for c in H["cases"]:
            cid = c["ids"][arm]
            pred = preds.get(cid, "MISSING")
            gold = c[goldk]
            ok = pred == gold if kind == "seal" else pred.replace("_", " ").lower() == str(gold).replace("_", " ").lower() or pred == gold
            trap = pred == c["trap_subj"] if kind == "seal" else False
            oks.append(ok)
            traps.append(trap)
            rows.append({"arm": arm, "kind": c["kind"], "id": cid, "pred": pred, "ok": ok, "trap": trap, "q": c["qh"] if "HOP" in arm else c["qs"]})
        k = sum(oks)
        summary[arm] = {
            "score": f"{k}/{n}",
            "trap": f"{sum(traps)}/{n}",
            "missing": sum(1 for c in H["cases"] if preds.get(c["ids"][arm], "MISSING") == "MISSING"),
            "wilson": wilson(k, n),
        }
    out = {"model": model, "n": n, "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}
    path = ROOT / "results" / f"future_unlock_{model}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
