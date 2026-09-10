#!/usr/bin/env python3
"""Score grev1_noprog QKEY / NONE isolation replies."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

H = json.loads((ROOT / "results" / "grev1_noprog_harness.json").read_text())
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def parse_dir(d: Path) -> dict:
    preds = {}
    if not d.exists():
        return preds
    for p in sorted(d.rglob("*.txt")):
        text = p.read_text()
        tagged = list(SEAL.finditer(text))
        for m in tagged:
            preds[m.group(1)] = m.group(2).strip()
        if not tagged:
            mm = re.search(r"GREV1_(?:QKEY|NONE)_\d+", text)
            cid = mm.group(0) if mm else None
            if cid and re.search(r"\bUNKNOWN\b", text, re.I):
                preds[cid] = "UNKNOWN"
    return preds


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    preds = parse_dir(ROOT / "results" / f"grev1_noprog_replies_{model}")
    by_arm: dict[str, list] = {}
    rows = []
    for c in H["cases"]:
        pred = preds.get(c["id"], "MISSING")
        if pred == c["gold"]:
            kind = "gold"
        elif pred.upper() == "UNKNOWN":
            kind = "unknown"
        elif pred == "MISSING":
            kind = "missing"
        elif c.get("trap") and pred == c["trap"]:
            kind = "trap"
        else:
            kind = "other"
        rec = {**{k: v for k, v in c.items() if k != "path"}, "pred": pred, "kind": kind, "ok": kind == "gold"}
        rows.append(rec)
        by_arm.setdefault(c["arm"], []).append(rec)
    summary = {}
    for arm, recs in by_arm.items():
        n = len(recs)
        k = sum(1 for r in recs if r["ok"])
        counts = {x: sum(1 for r in recs if r["kind"] == x) for x in ("gold", "trap", "unknown", "missing", "other")}
        summary[arm] = {"score": f"{k}/{n}", "wilson": wilson(k, n), "iso": True, **counts}
    out = {
        "model": model,
        "n": H["n"],
        "summary": summary,
        "nonclaim": H["nonclaim"],
        "rows": rows,
    }
    path = ROOT / "results" / f"grev1_noprog_{model}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
