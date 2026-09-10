#!/usr/bin/env python3
"""Score one-quiz-per-file opaque-rel isolation."""
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
H = json.loads((RESULTS / "wiki_cf_opaque_rel_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(.+)$", re.I | re.M)
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(.+)$", re.I | re.M)
SEAL_TOKEN = re.compile(r"E[0-9a-f]+", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().replace("_", " ")).lower().rstrip(".")


def parse_blob(text: str, kind: str) -> dict[str, str]:
    rx = PLAIN if kind == "plain" else SEAL
    return {m.group(1): m.group(2).strip() for m in rx.finditer(text)}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    arm = sys.argv[2] if len(sys.argv) > 2 else "SPAN_NL"
    kind = "plain" if arm == "PLAIN_NL" else "sealed"
    reply_dir = RESULTS / f"wiki_cf_opaque_rel_iso_replies_{model}" / arm
    n = H["n"]
    blob = ""
    if reply_dir.exists():
        blob = "\n".join(p.read_text() for p in sorted(reply_dir.glob("*.txt")))
    preds = parse_blob(blob, kind)
    oks, leaks, rows = [], [], []
    for c in H["cases"]:
        cid = c["ids"][arm]
        pred_raw = preds.get(cid, "MISSING")
        pred = pred_raw
        if kind == "sealed" and pred_raw not in {"MISSING", "UNKNOWN"}:
            toks = SEAL_TOKEN.findall(pred_raw)
            if toks:
                pred = toks[-1]
        if kind == "plain":
            ok = norm(pred) == norm(c["expect_plain"])
            leak = norm(pred) == norm(c["wiki_answer"])
        else:
            ok = pred == c["expect_seal"]
            leak = pred == c["wiki_seal"]
        oks.append(ok)
        leaks.append(leak)
        rows.append({"id": cid, "pred": pred, "ok": ok, "wiki_leak": leak, "missing": pred_raw == "MISSING"})
    k, L = sum(oks), sum(leaks)
    summary = {
        "score": f"{k}/{n}",
        "wiki_leak": f"{L}/{n}",
        "missing": sum(1 for r in rows if r["missing"]),
        "unknown": sum(1 for r in rows if str(r["pred"]).upper() == "UNKNOWN"),
        "wilson": wilson(k, n),
    }
    out = {
        "model": model,
        "arm": arm,
        "protocol": "one_quiz_per_file",
        "n": n,
        "summary": summary,
        "nonclaim": "Isolation. Not G-Rev1. Batched GPT SPAN 12/12 is not this protocol.",
        "rows": rows,
    }
    path = RESULTS / f"wiki_cf_opaque_rel_iso_{model}_{arm}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
