#!/usr/bin/env python3
"""Score spider_oir. Plain answers may be numeric or multi-word."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

RESULTS = ROOT / "results"
H = json.loads((RESULTS / "spider_oir_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(.+)$", re.I | re.M)
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ARMS = [("PLAIN_NL", "plain"), ("MILD_NL", "sealed"), ("GOLD_SQL", "sealed"), ("MODEL_SQL", "sealed")]


def nnum(s: str) -> str:
    s = s.strip().rstrip(".")
    try:
        f = float(s.replace(",", ""))
        if abs(f - round(f)) < 1e-6:
            return str(int(round(f)))
        return f"{f:.4f}".rstrip("0").rstrip(".")
    except Exception:
        return re.sub(r"\s+", " ", s).lower()


def parse(path: Path, kind: str) -> dict[str, str]:
    if not path.exists():
        return {}
    rx = PLAIN if kind == "plain" else SEAL
    return {m.group(1): m.group(2).strip() for m in rx.finditer(path.read_text())}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    reply = RESULTS / f"spider_replies_{model}"
    n = H["n"]
    summary, rows = {}, []
    for arm, kind in ARMS:
        preds = parse(reply / f"{arm}.txt", kind)
        oks = []
        for c in H["cases"]:
            cid = c["ids"][arm]
            pred = preds.get(cid, "MISSING")
            gold = c["expect_plain"] if kind == "plain" else c["expect_seal"]
            ok = nnum(pred) == nnum(gold) if kind == "plain" else pred == gold
            oks.append(ok)
            rows.append({"arm": arm, "id": cid, "db": c["db_id"], "gold": gold, "pred": pred, "ok": ok, "q": c["question"]})
        k = sum(oks)
        summary[arm] = {"score": f"{k}/{n}", "wilson": wilson(k, n), "missing": sum(1 for r in rows[-n:] if r["pred"] == "MISSING")}
    out = {"model": model, "n": n, "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}
    path = RESULTS / f"spider_oir_{model}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
