#!/usr/bin/env python3
"""Score hop-3 SAME rename (σ′) and G-Rev2 decoy MUT."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def parse_dir(d: Path) -> dict:
    out = {}
    if d.exists():
        for p in sorted(d.rglob("*.txt")):
            out.update({m.group(1): m.group(2).strip() for m in SEAL.finditer(p.read_text())})
    return out


def score(harness_name: str, replies_glob: str, model: str, trap_key: str | None):
    H = json.loads((ROOT / "results" / harness_name).read_text())
    preds = parse_dir(ROOT / "results" / replies_glob)
    rows = []
    by_arm: dict[str, list] = {}
    for c in H["cases"]:
        pred = preds.get(c["id"], "MISSING")
        kind = "other"
        if pred == c["gold"]:
            kind = "gold"
        elif pred.upper() == "UNKNOWN":
            kind = "unknown"
        elif pred == "MISSING":
            kind = "missing"
        elif trap_key and pred == c.get(trap_key):
            kind = "trap"
        rec = {**c, "pred": pred, "kind": kind, "ok": kind == "gold"}
        rows.append(rec)
        by_arm.setdefault(c["arm"], []).append(rec)
    summary = {}
    for arm, recs in by_arm.items():
        n = len(recs)
        k = sum(1 for r in recs if r["ok"])
        counts = {x: sum(1 for r in recs if r["kind"] == x) for x in ("gold", "trap", "unknown", "missing", "other")}
        summary[arm] = {"score": f"{k}/{n}", "wilson": wilson(k, n), **counts}
    outp = ROOT / "results" / f"{Path(harness_name).stem.replace('_harness','')}_{model}.json"
    extra = {"golds_all_differ": H.get("golds_all_differ")}
    outp.write_text(json.dumps({"model": model, "summary": summary, **extra, "nonclaim": H["nonclaim"], "rows": rows}, indent=2))
    print(outp.name, json.dumps(summary, indent=2))
    print("wrote", outp)


def main():
    which = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "auto"
    if which == "rename":
        score("hop3_rename_harness.json", f"hop3_rename_replies_{model}", model, "trap")
    elif which == "decoy":
        score("grev2_decoy_mut_harness.json", f"grev2_decoy_replies_{model}", model, None)
    else:
        raise SystemExit("rename|decoy")


if __name__ == "__main__":
    main()
