#!/usr/bin/env python3
"""Score wiki_cf PLAIN n=200 from shard replies and/or iso replies."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

H = json.loads((ROOT / "results" / "wiki_cf_n200_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(.+)$", re.I | re.M)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().replace("_", " ")).lower().rstrip(".")


def load_preds(model: str) -> dict[str, str]:
    preds = {}
    d = ROOT / "results" / f"wiki_cf_n200_replies_{model}"
    if not d.exists():
        return preds
    for p in d.rglob("*.txt"):
        preds.update({m.group(1): m.group(2).strip() for m in PLAIN.finditer(p.read_text())})
    return preds


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    preds = load_preds(model)
    n = H["n"]
    oks, leaks, rows = [], [], []
    for c in H["cases"]:
        pred = preds.get(c["id"], "MISSING")
        ok = norm(pred) == norm(c["expect_plain"])
        leak = norm(pred) == norm(c["wiki_answer"])
        oks.append(ok)
        leaks.append(leak)
        rows.append({"id": c["id"], "pred": pred, "ok": ok, "wiki_leak": leak})
    k, L = sum(oks), sum(leaks)
    miss = sum(1 for c in H["cases"] if preds.get(c["id"], "MISSING") == "MISSING")
    summary = {"score": f"{k}/{n}", "wiki_leak": f"{L}/{n}", "missing": miss, "wilson": wilson(k, n)}
    out = {
        "model": model,
        "n": n,
        "summary": summary,
        "falsifier": H["falsifier"],
        "nonclaim": H["nonclaim"],
        "rows": rows,
    }
    path = ROOT / "results" / f"wiki_cf_n200_{model}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
