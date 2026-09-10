#!/usr/bin/env python3
"""Score opaque_gen_v2: NL vs V2_NGRAM_COPY."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLY = RESULTS / "opaque_v2_replies"
H = json.loads((RESULTS / "opaque_v2_harness.json").read_text())
REV = H["rev"]


def unseal(s: str) -> str:
    out = []
    for tok in re.findall(r"E[0-9a-f]{12}|[^\s]+|\s+", s):
        out.append(REV.get(tok, tok) if re.fullmatch(r"E[0-9a-f]{12}", tok) else tok)
    return "".join(out).replace("_", " ")


def parse_ans(t: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(.+)", t)}


def parse_ev(t: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"EVIDENCE_SEALED\[([^\]]+)\]:\s*(.+)", t)}


def load(*names):
    for n in names:
        p = REPLY / n
        if p.exists():
            return p.read_text()
    return ""


def evid_recall(pred, gold):
    if not gold:
        return 0.0
    hits = 0
    for g in gold:
        gtoks = re.findall(r"E[0-9a-f]{12}", g)
        if gtoks and sum(1 for t in gtoks if t in pred) / len(gtoks) >= 0.55:
            hits += 1
    return hits / len(gold)


def rubric(plain, must):
    low = plain.lower()
    return (sum(1 for m in must if m.lower() in low) / len(must)) if must else 0.0


def main():
    nl_t = load("NL_composer.txt", "NL.txt")
    v2_t = load("V2_NGRAM_COPY_composer.txt", "V2.txt")
    nl_a, v2_a, v2_e = parse_ans(nl_t), parse_ans(v2_t), parse_ev(v2_t)

    rows = []
    for c in H["cases"]:
        gold, must = c["gold_evidence_sealed"], c["rubric_must"]
        nl_pred = nl_a.get(c["id_nl"], "MISSING")
        v2_pred = v2_a.get(c["id_v2"], "MISSING")
        nl_plain = unseal(nl_pred) if nl_pred not in ("MISSING", "UNKNOWN") else nl_pred
        v2_plain = unseal(v2_pred) if v2_pred not in ("MISSING", "UNKNOWN") else v2_pred
        nl_rub = rubric(nl_plain, must)
        v2_rub = rubric(v2_plain, must)
        v2_er = evid_recall(v2_e.get(c["id_v2"], ""), gold)
        # For V2: if retrieve already hit gold, evidence may be R-lines containing gold —
        # also accept rubric alone when retrieve_gold_hit>=0.8 and rubric>=0.5
        v2_pass = (v2_er >= 0.5 and v2_rub >= 0.5) or (
            c["opaque_retrieve_gold_hit"] >= 0.8 and v2_rub >= 0.5 and v2_pred.upper() != "UNKNOWN"
        )
        nl_pass = nl_rub >= 0.5 and nl_pred.upper() != "UNKNOWN"
        rows.append(
            {
                "id": c["id_nl"].replace("_NL", ""),
                "doc": c["doc"],
                "retrieve_hit": c["opaque_retrieve_gold_hit"],
                "nl_pass": nl_pass,
                "nl_rubric": round(nl_rub, 2),
                "v2_pass": v2_pass,
                "v2_rubric": round(v2_rub, 2),
                "v2_evidence_recall": round(v2_er, 2),
                "nl_unsealed": nl_plain[:100],
                "v2_unsealed": v2_plain[:120],
            }
        )

    n = len(rows)
    pol = [r for r in rows if r["doc"] != "feta"]
    fet = [r for r in rows if r["doc"] == "feta"]

    def rate(rs, f):
        return f"{sum(1 for r in rs if r[f])}/{len(rs)}"

    out = {
        "n": n,
        "theory": H.get("theory"),
        "opaque_retrieve_mean_gold_hit": H.get("opaque_retrieve_mean_gold_hit"),
        "summary": {
            "NL_pass": rate(rows, "nl_pass"),
            "V2_pass": rate(rows, "v2_pass"),
            "policy_NL": rate(pol, "nl_pass"),
            "policy_V2": rate(pol, "v2_pass"),
            "feta_NL": rate(fet, "nl_pass"),
            "feta_V2": rate(fet, "v2_pass"),
            "mean_NL_rubric": round(sum(r["nl_rubric"] for r in rows) / n, 3),
            "mean_V2_rubric": round(sum(r["v2_rubric"] for r in rows) / n, 3),
        },
        "rows": rows,
        "claim": H.get("claim"),
    }
    (RESULTS / "opaque_v2_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["summary"], indent=2))


if __name__ == "__main__":
    main()
