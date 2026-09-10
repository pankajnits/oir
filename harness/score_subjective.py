#!/usr/bin/env python3
"""Score opaque subjective generation: NL / EVIDENCE / SEAL_RETRIEVE (+ diagnostic EH)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLY = RESULTS / "subjective_replies"
H = json.loads((RESULTS / "subjective_harness.json").read_text())
REV = H["rev"]


def unseal_text(s: str) -> str:
    out = []
    for tok in re.findall(r"E[0-9a-f]{12}|[^\s]+|\s+", s):
        if re.fullmatch(r"E[0-9a-f]{12}", tok):
            out.append(REV.get(tok, tok))
        else:
            out.append(tok)
    return "".join(out).replace("_", " ")


def parse_answers(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(.+)", text)
    }


def parse_evidence(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"EVIDENCE_SEALED\[([^\]]+)\]:\s*(.+)", text)
    }


def load_reply(*names: str) -> str:
    for n in names:
        p = REPLY / n
        if p.exists():
            return p.read_text()
    return ""


def evidence_recall(pred_ev: str, gold_sealed: list[str]) -> float:
    if not gold_sealed:
        return 0.0
    hits = 0
    for g in gold_sealed:
        gtoks = [t for t in g.split() if t.startswith("E") and re.fullmatch(r"E[0-9a-f]{12}", t)]
        if not gtoks:
            continue
        ok = sum(1 for t in gtoks if t in pred_ev) / len(gtoks)
        hits += int(ok >= 0.6)
    return hits / max(1, len(gold_sealed))


def rubric_hit(unsealed: str, must: list[str]) -> float:
    low = unsealed.lower()
    if not must:
        return 0.0
    return sum(1 for m in must if m.lower() in low) / len(must)


def score_one(ans, ev, cid, gold, must):
    pred = ans.get(cid, "MISSING")
    spans = ev.get(cid, "")
    plain = unseal_text(pred) if pred not in ("MISSING", "UNKNOWN") else pred
    return pred, plain, evidence_recall(spans, gold), rubric_hit(plain, must)


def main():
    packs = {
        "nl": (load_reply("NL_composer.txt", "NL.txt"), "id_nl"),
        "ev": (load_reply("EVIDENCE_composer.txt", "EVIDENCE.txt"), "id_ev"),
        "sr": (load_reply("SEAL_RETRIEVE_composer.txt", "SEAL_RETRIEVE.txt"), "id_sr"),
        "eh": (load_reply("EV_HANDLES_composer.txt", "EV_HANDLES.txt"), "id_eh"),
    }
    parsed = {k: (parse_answers(t), parse_evidence(t), kid) for k, (t, kid) in packs.items()}

    rows = []
    for c in H["cases"]:
        gold, must = c["gold_evidence_sealed"], c["rubric_must"]
        row = {
            "id": c["id_nl"].replace("_NL", ""),
            "doc": c["doc"],
            "opaque_retrieve_gold_hit": c.get("opaque_retrieve_gold_hit"),
            "question": c["question"][:100],
        }
        for key, (ans, ev, id_field) in parsed.items():
            cid = c.get(id_field)
            if not cid:
                continue
            pred, plain, er, rub = score_one(ans, ev, cid, gold, must)
            if key == "nl":
                passed = rub >= 0.5 and pred.upper() != "UNKNOWN"
            else:
                passed = er >= 0.5 and rub >= 0.5
            row[f"{key}_rubric"] = round(rub, 2)
            row[f"{key}_evidence_recall"] = round(er, 2)
            row[f"{key}_pass"] = passed
            row[f"{key}_unsealed"] = plain[:120]
        rows.append(row)

    n = len(rows)

    def rate(field):
        return f"{sum(1 for r in rows if r.get(field))}/{n}"

    def mean(field):
        vals = [r[field] for r in rows if field in r and r[field] is not None]
        return round(sum(vals) / max(1, len(vals)), 3)

    out = {
        "n": n,
        "claim": H.get("claim"),
        "opaque_retrieve_mean_gold_hit": H.get("opaque_retrieve_mean_gold_hit"),
        "summary": {
            "NL_pass": rate("nl_pass"),
            "EVIDENCE_pass": rate("ev_pass"),
            "SEAL_RETRIEVE_pass": rate("sr_pass"),
            "EV_HANDLES_diagnostic_pass": rate("eh_pass"),
            "mean_NL_rubric": mean("nl_rubric"),
            "mean_EV_evidence_recall": mean("ev_evidence_recall"),
            "mean_EV_rubric": mean("ev_rubric"),
            "mean_SR_evidence_recall": mean("sr_evidence_recall"),
            "mean_SR_rubric": mean("sr_rubric"),
            "mean_EH_rubric": mean("eh_rubric"),
        },
        "rows": rows,
        "scoring": (
            "CLAIM path = SEAL_RETRIEVE (opaque seal-overlap find + generate). "
            "EV_HANDLES = diagnostic oracle only. "
            "Pass: NL rubric>=0.5; others evidence_recall>=0.5 and rubric>=0.5."
        ),
    }
    (RESULTS / "subjective_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["summary"], indent=2))
    print("opaque_retrieve_mean_gold_hit", out["opaque_retrieve_mean_gold_hit"])


if __name__ == "__main__":
    main()
