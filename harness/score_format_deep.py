#!/usr/bin/env python3
"""Score format_deep: gold vs trap vs UNKNOWN."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

H = json.loads((ROOT / "results" / "format_deep_harness.json").read_text())
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def parse_dir(d: Path) -> dict:
    out = {}
    if d.exists():
        for p in sorted(d.rglob("*.txt")):
            out.update({m.group(1): m.group(2).strip() for m in SEAL.finditer(p.read_text())})
    return out


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    preds = parse_dir(ROOT / "results" / f"format_deep_replies_{model}")
    by_arm: dict[str, list] = {}
    rows = []
    for c in H["cases"]:
        pred = preds.get(c["id"], "MISSING")
        kind = "other"
        if pred == c["gold"]:
            kind = "gold"
        elif pred.upper() == "UNKNOWN":
            kind = "unknown"
        elif pred == "MISSING":
            kind = "missing"
        elif c.get("trap") and pred == c["trap"]:
            kind = "trap"
        rec = {**c, "pred": pred, "kind": kind, "ok": kind == "gold"}
        rows.append(rec)
        by_arm.setdefault(c["arm"], []).append(rec)
    summary = {}
    for arm, recs in by_arm.items():
        n = len(recs)
        k = sum(1 for r in recs if r["ok"])
        counts = {x: sum(1 for r in recs if r["kind"] == x) for x in ("gold", "trap", "unknown", "missing", "other")}
        summary[arm] = {"score": f"{k}/{n}", "wilson": wilson(k, n), "iso": recs[0].get("iso"), **counts}
    path = ROOT / "results" / f"format_deep_{model}.json"
    path.write_text(
        json.dumps({"model": model, "n": H["n"], "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2)
    )
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
