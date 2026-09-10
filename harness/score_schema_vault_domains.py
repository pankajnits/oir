#!/usr/bin/env python3
"""Score schema_vault_domains."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

RESULTS = ROOT / "results"
H = json.loads((RESULTS / "schema_vault_domains_harness.json").read_text())
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ARMS = ["MILD_PROG", "MILD_NL", "STRICT_PROG", "STRICT_NL"]


def parse(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {m.group(1): m.group(2) for m in SEAL.finditer(path.read_text())}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    reply = RESULTS / f"sv_replies_{model}"
    n = H["n"]
    summary, rows = {}, []
    by_domain = {d: {a: [] for a in ARMS} for d in ("EHR", "LEDGER", "SBOM")}
    for arm in ARMS:
        preds = parse(reply / f"{arm}.txt")
        oks = []
        for c in H["cases"]:
            cid = c["ids"][arm]
            pred = preds.get(cid, "MISSING")
            ok = pred == c["expect_seal"]
            oks.append(ok)
            by_domain[c["domain"]][arm].append(ok)
            rows.append(
                {
                    "arm": arm,
                    "id": cid,
                    "domain": c["domain"],
                    "gold": c["expect_seal"],
                    "pred": pred,
                    "ok": ok,
                    "keys": c["keys"],
                }
            )
        k = sum(oks)
        summary[arm] = {
            "score": f"{k}/{n}",
            "missing": sum(1 for r in rows[-n:] if r["pred"] == "MISSING"),
            "wilson": wilson(k, n),
        }
    domain_scores = {
        d: {a: f"{sum(v[a])}/{len(v[a])}" for a in ARMS} for d, v in by_domain.items()
    }
    mp, mn, sp, sn = (int(summary[a]["score"].split("/")[0]) for a in ARMS)
    verdict = (
        f"MILD_PROG {mp}/{n}; MILD_NL {mn}/{n}; STRICT_PROG {sp}/{n}; STRICT_NL {sn}/{n}. "
        "Hyphenated instance IDs (pat-1000, acct-4000, GHSA-*) survive EntitySeal.text and "
        "appear in STRICT_NL questions — copy-and-walk, not sealed-English. "
        "Not G-Rev1. Not privacy."
    )
    out = {
        "model": model,
        "n": n,
        "summary": summary,
        "by_domain": domain_scores,
        "verdict": verdict,
        "nonclaim": H["nonclaim"],
        "rows": rows,
    }
    path = RESULTS / f"schema_vault_domains_{model}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps({"summary": summary, "by_domain": domain_scores, "verdict": verdict}, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
