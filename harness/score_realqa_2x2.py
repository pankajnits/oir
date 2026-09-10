#!/usr/bin/env python3
"""Score realqa_2x2 replies. Plain answers may be multi-word; sealed are tokens."""
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
H = json.loads((RESULTS / "realqa_2x2_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(.+)$", re.I | re.M)
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)

CORE_ARMS = [
    ("PLAIN_NL", "plain"),
    ("PLAIN_PROG", "plain"),
    ("SEAL_NL", "sealed"),
    ("SEAL_PROG", "sealed"),
]
EXTRA_ARMS = [
    ("SPAN_NL", "sealed"),
]
FAMILIES = [
    ("ceo", H["ceo"]),
    ("wiki", H["wiki"]),
    ("wtq", H["wtq"]),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.strip().strip("\"'`").rstrip(".")
    s = re.sub(r"\s+", " ", s).lower()
    s = s.replace("_", " ")
    return s


def parse(path: Path, kind: str) -> dict[str, str]:
    if not path.exists():
        return {}
    rx = PLAIN if kind == "plain" else SEAL
    return {m.group(1): m.group(2).strip() for m in rx.finditer(path.read_text())}


def match_plain(pred: str, gold: str) -> bool:
    if pred.upper() == "MISSING":
        return False
    p, g = norm(pred), norm(gold)
    if p == g:
        return True
    # allow first gold piece when dataset uses | alternatives
    return p == norm(gold.split("|")[0])


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    reply_root = RESULTS / f"realqa_replies_{model}"
    families_out = {}
    all_rows = []
    for fam_dir, fam in FAMILIES:
        n = fam["n"]
        summary = {}
        for arm, kind in CORE_ARMS + EXTRA_ARMS:
            if any(arm not in c["ids"] for c in fam["cases"]):
                continue
            preds = parse(reply_root / fam_dir / f"{arm}.txt", kind)
            oks = []
            for c in fam["cases"]:
                cid = c["ids"][arm]
                pred = preds.get(cid, "MISSING")
                gold = c["expect_plain"] if kind == "plain" else c["expect_seal"]
                ok = match_plain(pred, gold) if kind == "plain" else pred == gold
                oks.append(ok)
                all_rows.append(
                    {
                        "family": fam_dir,
                        "arm": arm,
                        "id": cid,
                        "gold": gold,
                        "pred": pred,
                        "ok": ok,
                        "question": c.get("question"),
                        "start_seal_in_span_q": c.get("start_seal_in_span_q"),
                    }
                )
            k = sum(oks)
            summary[arm] = {
                "score": f"{k}/{n}",
                "missing": sum(1 for c in fam["cases"] if preds.get(c["ids"][arm], "MISSING") == "MISSING"),
                "wilson": wilson(k, n),
            }
        # ID map used in builder:
        # CEO_PLAINNL, CEO_PLAINPROG, CEO_SEALNL, CEO_SEALPROG
        families_out[fam_dir] = {
            "n": n,
            "source": fam.get("source"),
            "summary": summary,
            "verdict": _verdict(summary, n),
        }
    out = {
        "model": model,
        "design": "opacity × binder 2×2",
        "families": families_out,
        "rows": all_rows,
        "nonclaim": H["nonclaim"],
    }
    path = RESULTS / f"realqa_2x2_{model}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps({k: v["summary"] | {"verdict": v["verdict"]} for k, v in families_out.items()}, indent=2))
    print("wrote", path)


def _verdict(summary: dict, n: int) -> str:
    def k(arm):
        return int(summary[arm]["score"].split("/")[0])

    pnl, pp, snl, sp = k("PLAIN_NL"), k("PLAIN_PROG"), k("SEAL_NL"), k("SEAL_PROG")
    if pnl >= n - 1 and pp == n and sp == n and snl <= 1:
        return "SUPPORTED: PLAIN_NL ≈ PLAIN_PROG ≈ SEAL_PROG ≫ SEAL_NL"
    if pp == n and sp == n and snl <= 1 and pnl <= n // 2:
        return "SCOPED: binders restore; PLAIN_NL weaker — plan helps even on readable symbols"
    return f"MIXED: PLAIN_NL {pnl}/{n}; PLAIN_PROG {pp}/{n}; SEAL_PROG {sp}/{n}; SEAL_NL {snl}/{n}"


if __name__ == "__main__":
    main()
