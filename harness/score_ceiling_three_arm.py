#!/usr/bin/env python3
"""Score three-arm ceiling replies."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLY = RESULTS / "ceiling_replies"
H = json.loads((RESULTS / "ceiling_three_arm_harness.json").read_text())


def load(*names):
    for n in names:
        p = REPLY / n
        if p.exists():
            return p.read_text()
    return ""


def parse(tag: str, text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(rf"{tag}\[([^\]]+)\]:\s*(\S+)", text)
    }


def main():
    plain = parse("ANSWER_PLAIN", load("PLAIN_PROG_composer.txt", "PLAIN_PROG.txt"))
    sealp = parse("ANSWER_SEALED", load("SEAL_PROG_composer.txt", "SEAL_PROG.txt"))
    sealn = parse("ANSWER_SEALED", load("SEAL_NL_composer.txt", "SEAL_NL.txt"))

    rows = []
    for c in H["cases"]:
        pa = plain.get(c["id_plain"], "MISSING")
        pb = sealp.get(c["id_sealprog"], "MISSING")
        pc = sealn.get(c["id_sealnl"], "MISSING")
        ok_a = pa == c["expect_plain"]
        ok_b = pb == c["expect_seal"]
        ok_c = pc == c["expect_seal"]
        stop_c = pc == c["company_seal"]
        rows.append(
            {
                "i": c["i"],
                "person": c["person"],
                "hq": c["hq"],
                "plain_ok": ok_a,
                "sealprog_ok": ok_b,
                "sealnl_ok": ok_c,
                "sealnl_company_stop": stop_c,
                "pred_plain": pa,
                "pred_sealprog": pb,
                "pred_sealnl": pc,
            }
        )

    n = len(rows)
    out = {
        "n": n,
        "summary": {
            "PLAIN_PROG": f"{sum(r['plain_ok'] for r in rows)}/{n}",
            "SEAL_PROG": f"{sum(r['sealprog_ok'] for r in rows)}/{n}",
            "SEAL_NL": f"{sum(r['sealnl_ok'] for r in rows)}/{n}",
            "SEAL_NL_company_stop": f"{sum(r['sealnl_company_stop'] for r in rows)}/{n}",
            "SealRouter_ceiling": H.get("sealrouter_ceiling"),
        },
        "rows": rows,
        "claim": H.get("claim"),
        "verdict": None,
    }
    a = sum(r["plain_ok"] for r in rows)
    b = sum(r["sealprog_ok"] for r in rows)
    c = sum(r["sealnl_ok"] for r in rows)
    if a >= n - 1 and b >= n - 1 and c <= n // 3:
        out["verdict"] = "SUPPORTED: PLAIN≈SEAL_PROG ≫ SEAL_NL"
    elif b >= n - 1 and c <= n // 3:
        out["verdict"] = "PARTIAL: SEAL_PROG saturates; PLAIN check needed"
    else:
        out["verdict"] = "RETEST / inspect rows"

    (RESULTS / "ceiling_three_arm_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["summary"], indent=2))
    print("verdict:", out["verdict"])


if __name__ == "__main__":
    main()
