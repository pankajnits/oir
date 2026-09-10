#!/usr/bin/env python3
"""Score e2e binder-family + PDF-channel results."""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "e2e_binder_harness.json").read_text())
REPLY = RESULTS / "e2e_replies"


def parse_sealed(t):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", t)}


def parse_num(t):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"ANSWER_NUM\[([^\]]+)\]:\s*(\S+)", t)}


def main():
    REPLY.mkdir(parents=True, exist_ok=True)
    # map filename stem -> form filter
    files = {
        "DSL_FILTER": ("DSL", "sealed"),
        "DSL_COUNT": ("COUNT", "num"),
        "PATH3": ("PATH3", "sealed"),
        "TOOL_ROUTER": ("TOOL", "sealed"),
        "NL_CTRL": ("NL", "sealed"),
        "PDF_NL": (None, "sealed"),  # form NL with channel
        "PDF_PROG": (None, "sealed"),
    }
    report = {"table": {}, "pdf_meta": H.get("pdf_meta")}
    for stem, (form, mode) in files.items():
        p = REPLY / f"{stem}_composer.txt"
        if not p.exists():
            report["table"][stem] = {"status": "pending"}
            continue
        text = p.read_text()
        if stem.startswith("PDF_"):
            want_form = "NL" if stem.endswith("NL") else "PROG"
            rows = [c for c in H["cases"] if c.get("form") == want_form and str(c.get("channel", "")).startswith("PDF_")]
        elif form == "NL":
            rows = [c for c in H["cases"] if c["form"] == "NL" and not c.get("channel")]
        else:
            rows = [c for c in H["cases"] if c["form"] == form]
        ok = stops = unk = 0
        detail = []
        if mode == "num":
            preds = parse_num(text)
            for c in rows:
                pred = preds.get(c["id"], "MISSING")
                hit = str(pred) == str(c["expect_num"])
                ok += int(hit)
                detail.append({"id": c["id"], "ok": hit, "pred": pred, "expect": c["expect_num"]})
        else:
            preds = parse_sealed(text)
            for c in rows:
                pred = preds.get(c["id"], "MISSING")
                hit = pred == c["expect"]
                ok += int(hit)
                st = pred == c.get("intermediate_company")
                stops += int(bool(st))
                unk += int(pred == "UNKNOWN")
                detail.append({"id": c["id"], "ok": hit, "pred": pred, "expect": c["expect"], "channel": c.get("channel")})
        # split PDF by channel
        if stem.startswith("PDF_"):
            for ch in ("PDF_TEXT", "PDF_OCR"):
                sub = [d for d in detail if d.get("channel") == ch]
                if not sub:
                    continue
                sok = sum(1 for d in sub if d["ok"])
                report["table"][f"{stem}_{ch}"] = {"score": f"{sok}/{len(sub)}", "n": len(sub)}
        report["table"][stem] = {
            "score": f"{ok}/{len(rows)}",
            "n": len(rows),
            "company_stops": stops,
            "unknown": unk,
            "detail": detail,
        }
    (RESULTS / "e2e_binder_results.json").write_text(json.dumps(report, indent=2))
    slim = {
        k: {kk: vv for kk, vv in v.items() if kk != "detail"} if isinstance(v, dict) else v
        for k, v in report["table"].items()
    }
    print(json.dumps({"table": slim, "ocr_ok": report["pdf_meta"].get("ocr_ok") if report["pdf_meta"] else None}, indent=2))


if __name__ == "__main__":
    main()
