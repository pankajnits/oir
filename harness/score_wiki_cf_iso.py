#!/usr/bin/env python3
"""Score isolated 2Wiki-CF PLAIN replies (subset or full)."""
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


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt56_iso"
    d = ROOT / "results" / f"wiki_cf_n200_replies_{model}"
    preds = {}
    if d.exists():
        for p in d.rglob("*.txt"):
            preds.update({m.group(1): m.group(2).strip() for m in PLAIN.finditer(p.read_text())})
    rows = []
    for c in H["cases"]:
        if c["id"] not in preds:
            continue
        pred = preds[c["id"]]
        ok = norm(pred) == norm(c["expect_plain"])
        leak = norm(pred) == norm(c["wiki_answer"])
        shard = c["i"] // 50
        rows.append({"id": c["id"], "i": c["i"], "shard": shard, "pred": pred, "ok": ok, "wiki_leak": leak})
    n = len(rows)
    k = sum(r["ok"] for r in rows)
    L = sum(r["wiki_leak"] for r in rows)
    by = {}
    for r in rows:
        by.setdefault(r["shard"], {"n": 0, "ok": 0, "leak": 0})
        by[r["shard"]]["n"] += 1
        by[r["shard"]]["ok"] += int(r["ok"])
        by[r["shard"]]["leak"] += int(r["wiki_leak"])
    summary = {
        "n_scored": n,
        "score": f"{k}/{n}" if n else "0/0",
        "wiki_leak": f"{L}/{n}" if n else "0/0",
        "wilson": wilson(k, n) if n else None,
        "by_shard": {str(s): f"{v['ok']}/{v['n']} leak {v['leak']}/{v['n']}" for s, v in sorted(by.items())},
    }
    out = ROOT / "results" / f"wiki_cf_iso_{model}.json"
    out.write_text(json.dumps({"model": model, "summary": summary, "rows": rows, "nonclaim": "Isolation of PLAIN_NL CF. Not G-Rev1."}, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
