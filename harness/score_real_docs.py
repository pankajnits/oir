#!/usr/bin/env python3
"""Score real-docs Excel NL vs PROG replies."""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "real_docs_excel_harness.json").read_text())
REPLY = RESULTS / "real_docs_replies"


def parse(text):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", text)}


def score(form_tag_prefix, answers):
    # cases have id like XD_WIKI_XLSX_NL_0
    rows = [c for c in H["cases"] if c["form"] == form_tag_prefix.split("_")[-1] or True]
    # better: match by form and tag in id
    form = "NL" if form_tag_prefix.endswith("NL") else "PROG"
    tag = "WIKI_XLSX" if "WIKI" in form_tag_prefix else "OD500_XLSX"
    rows = [c for c in H["cases"] if c["form"] == form and c["tag"] == tag]
    ok = stops = unk = 0
    detail = []
    for c in rows:
        pred = answers.get(c["id"], "MISSING")
        hit = pred == c["expect"]
        ok += int(hit)
        st = pred == c["intermediate_company"]
        stops += int(st)
        unk += int(pred == "UNKNOWN")
        detail.append({"id": c["id"], "ok": hit, "pred": pred, "expect": c["expect"], "stop": st})
    return {"form": form, "tag": tag, "score": f"{ok}/{len(rows)}", "company_stops": stops, "unknown": unk, "detail": detail}


def main():
    REPLY.mkdir(parents=True, exist_ok=True)
    report = {"table": {}, "workbooks": H["workbooks"]}
    mapping = {
        "WIKI_NL": "WIKI_NL_composer.txt",
        "WIKI_PROG": "WIKI_PROG_composer.txt",
        "OD500_NL": "OD500_NL_composer.txt",
        "OD500_PROG": "OD500_PROG_composer.txt",
    }
    for key, fname in mapping.items():
        p = REPLY / fname
        if not p.exists():
            report["table"][key] = {"status": "pending"}
            continue
        report["table"][key] = score(key, parse(p.read_text()))
        # drop detail from summary table view
        summary = {k: v for k, v in report["table"][key].items() if k != "detail"}
        report["table"][key] = {**summary, "detail": report["table"][key]["detail"]}
    (RESULTS / "real_docs_excel_results.json").write_text(json.dumps(report, indent=2))
    slim = {k: {kk: vv for kk, vv in v.items() if kk != "detail"} if isinstance(v, dict) else v for k, v in report["table"].items()}
    print(json.dumps({"table": slim, "workbooks": report["workbooks"]}, indent=2))


if __name__ == "__main__":
    main()
