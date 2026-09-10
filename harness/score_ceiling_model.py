#!/usr/bin/env python3
"""Score three-arm ceiling from a model-tagged reply directory."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "ceiling_three_arm_harness.json").read_text())


def parse(tag: str, text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(rf"{tag}\[([^\]]+)\]:\s*(\S+)", text, re.I)
    }


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "composer"
    reply = RESULTS / f"ceiling_replies_{model}"
    if not reply.exists():
        reply = RESULTS / "ceiling_replies"

    def load(stem: str) -> str:
        for n in (f"{stem}.txt", f"{stem}_{model}.txt", f"{stem}_composer.txt"):
            p = reply / n
            if p.exists():
                return p.read_text()
        return ""

    plain = parse("ANSWER_PLAIN", load("PLAIN_PROG"))
    sealp = parse("ANSWER_SEALED", load("SEAL_PROG"))
    sealn = parse("ANSWER_SEALED", load("SEAL_NL"))

    rows = []
    for c in H["cases"]:
        pa, pb, pc = plain.get(c["id_plain"], "MISSING"), sealp.get(c["id_sealprog"], "MISSING"), sealn.get(c["id_sealnl"], "MISSING")
        rows.append(
            {
                "i": c["i"],
                "person": c["person"],
                "plain_ok": pa == c["expect_plain"],
                "sealprog_ok": pb == c["expect_seal"],
                "sealnl_ok": pc == c["expect_seal"],
                "sealnl_company_stop": pc == c["company_seal"],
                "pred_plain": pa,
                "pred_sealprog": pb,
                "pred_sealnl": pc,
            }
        )
    n = len(rows)
    summary = {
        "PLAIN_PROG": f"{sum(r['plain_ok'] for r in rows)}/{n}",
        "SEAL_PROG": f"{sum(r['sealprog_ok'] for r in rows)}/{n}",
        "SEAL_NL": f"{sum(r['sealnl_ok'] for r in rows)}/{n}",
        "SEAL_NL_company_stop": f"{sum(r['sealnl_company_stop'] for r in rows)}/{n}",
        "SealRouter_ceiling": H.get("sealrouter_ceiling"),
    }
    out = {"model": model, "n": n, "summary": summary, "rows": rows, "reply_dir": str(reply)}
    a, b, c = (sum(r[k] for r in rows) for k in ("plain_ok", "sealprog_ok", "sealnl_ok"))
    if a >= n - 1 and b >= n - 1 and c <= n // 3:
        out["verdict"] = "SUPPORTED: PLAIN≈SEAL_PROG ≫ SEAL_NL"
    elif b == 0 and c == 0 and a >= n - 1:
        out["verdict"] = "SCOPED: PLAIN ok; opaque PATH and NL fail (model-dependent)"
    else:
        out["verdict"] = f"MIXED: PLAIN {a}/{n}; SEAL_PROG {b}/{n}; SEAL_NL {c}/{n}"
    path = RESULTS / f"ceiling_three_arm_{model}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(out["verdict"])
    print("wrote", path)


if __name__ == "__main__":
    main()
