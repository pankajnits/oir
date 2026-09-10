#!/usr/bin/env python3
"""Score wiki_cf: CF gold vs Wikipedia leak."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

RESULTS = ROOT / "results"
H = json.loads((RESULTS / "wiki_cf_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(.+)$", re.I | re.M)
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ARMS = [("PLAIN_NL", "plain"), ("SPAN_NL", "sealed"), ("SEAL_PROG", "sealed"), ("MODEL_PLAN", "sealed")]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().replace("_", " ")).lower().rstrip(".")


def parse(path: Path, kind: str) -> dict[str, str]:
    if not path.exists():
        return {}
    rx = PLAIN if kind == "plain" else SEAL
    return {m.group(1): m.group(2).strip() for m in rx.finditer(path.read_text())}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    reply = RESULTS / f"wiki_cf_replies_{model}"
    n = H["n"]
    summary, rows = {}, []
    for arm, kind in ARMS:
        preds = parse(reply / f"{arm}.txt", kind)
        oks, leaks = [], []
        for c in H["cases"]:
            cid = c["ids"][arm]
            pred = preds.get(cid, "MISSING")
            if kind == "plain":
                ok = norm(pred) == norm(c["expect_plain"])
                leak = norm(pred) == norm(c["wiki_answer"])
            else:
                ok = pred == c["expect_seal"]
                leak = pred == c["wiki_seal"]
            oks.append(ok)
            leaks.append(leak)
            rows.append({"arm": arm, "id": cid, "pred": pred, "ok": ok, "wiki_leak": leak, "q": c["question"]})
        k, L = sum(oks), sum(leaks)
        summary[arm] = {
            "score": f"{k}/{n}",
            "wiki_leak": f"{L}/{n}",
            "missing": sum(1 for c in H["cases"] if preds.get(c["ids"][arm], "MISSING") == "MISSING"),
            "wilson": wilson(k, n),
        }
    out = {
        "model": model,
        "n": n,
        "summary": summary,
        "falsifier": H["falsifier"],
        "nonclaim": H["nonclaim"],
        "rows": rows,
    }
    path = RESULTS / f"wiki_cf_{model}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
