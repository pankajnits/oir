#!/usr/bin/env python3
"""Score wiki_cf_n32 PLAIN_NL."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

H = json.loads((ROOT / "results" / "wiki_cf_n32_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(.+)$", re.I | re.M)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().replace("_", " ")).lower().rstrip(".")


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    path = ROOT / "results" / f"wiki_cf_n32_replies_{model}" / "PLAIN_NL.txt"
    preds = {}
    if path.exists():
        preds = {m.group(1): m.group(2).strip() for m in PLAIN.finditer(path.read_text())}
    n = H["n"]
    oks, leaks, rows = [], [], []
    for c in H["cases"]:
        pred = preds.get(c["id"], "MISSING")
        ok = norm(pred) == norm(c["expect_plain"])
        leak = norm(pred) == norm(c["wiki_answer"])
        oks.append(ok)
        leaks.append(leak)
        rows.append({"id": c["id"], "pred": pred, "ok": ok, "wiki_leak": leak, "q": c["question"]})
    k, L = sum(oks), sum(leaks)
    summary = {"score": f"{k}/{n}", "wiki_leak": f"{L}/{n}", "missing": sum(p == "MISSING" for p in preds.values() or [0]), "wilson": wilson(k, n)}
    # missing count from cases
    summary["missing"] = sum(1 for c in H["cases"] if preds.get(c["id"], "MISSING") == "MISSING")
    out = {"model": model, "n": n, "summary": summary, "falsifier": H["falsifier"], "nonclaim": H["nonclaim"], "rows": rows}
    op = ROOT / "results" / f"wiki_cf_n32_{model}.json"
    op.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    print("wrote", op)


if __name__ == "__main__":
    main()
