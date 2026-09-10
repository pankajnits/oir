#!/usr/bin/env python3
"""Score paired renaming σ/σ′ SEAL_PROG factorial."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLIES = RESULTS / "rename_replies"
HARNESS = RESULTS / "rename_equivariance_harness.json"

ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def load_preds(path: Path) -> dict[str, str]:
    text = path.read_text()
    return {m.group(1): m.group(2) for m in ANS_RE.finditer(text)}


def main():
    harness = json.loads(HARNESS.read_text())
    by_arm: dict[str, list] = {"SIGMA": [], "SIGMA_PRIME": []}
    preds = {}
    for arm in ("SIGMA", "SIGMA_PRIME"):
        p = REPLIES / f"{arm}_composer.txt"
        preds[arm] = load_preds(p) if p.exists() else {}

    rows = []
    for c in harness["cases"]:
        arm = c["arm"]
        pred = preds.get(arm, {}).get(c["id"], "")
        ok = pred == c["gold_seal"]
        by_arm[arm].append(ok)
        rows.append({**c, "pred": pred, "ok": ok})

    # Cross-key: same i should have different golds and both ok → renaming
    n = harness["n_per_key"]
    cross = []
    for i in range(n):
        a = next(r for r in rows if r["arm"] == "SIGMA" and r["i"] == i)
        b = next(r for r in rows if r["arm"] == "SIGMA_PRIME" and r["i"] == i)
        cross.append(
            {
                "i": i,
                "person": a["person"],
                "gold_differ": a["gold_seal"] != b["gold_seal"],
                "both_ok": a["ok"] and b["ok"],
            }
        )

    summary = {
        "SIGMA": f"{sum(by_arm['SIGMA'])}/{len(by_arm['SIGMA'])}",
        "SIGMA_PRIME": f"{sum(by_arm['SIGMA_PRIME'])}/{len(by_arm['SIGMA_PRIME'])}",
        "golds_differ_all": all(x["gold_differ"] for x in cross),
        "paired_both_ok": f"{sum(x['both_ok'] for x in cross)}/{len(cross)}",
    }
    supported = (
        sum(by_arm["SIGMA"]) == n
        and sum(by_arm["SIGMA_PRIME"]) == n
        and summary["golds_differ_all"]
    )
    out = {
        "summary": summary,
        "cross": cross,
        "rows": rows,
        "verdict": (
            "SUPPORTED: renaming-equivariant SEAL_PROG (σ≈σ′ accuracy; seals differ)"
            if supported
            else "PARTIAL/FAIL — check replies"
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "rename_equivariance_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(out["verdict"])


if __name__ == "__main__":
    main()
