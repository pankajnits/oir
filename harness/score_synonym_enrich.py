#!/usr/bin/env python3
"""Score synonym-enrich MUT replies."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLY = RESULTS / "synonym_enrich_replies"
H = json.loads((RESULTS / "synonym_enrich_harness.json").read_text())


def parse(text: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", text, flags=re.I)
    }


def main():
    by = defaultdict(lambda: {"ok": 0, "n": 0, "company_stop": 0, "unknown": 0, "detail": []})
    for form in ["RAW", "SYN", "SYN_LIVE", "CANON", "PROG"]:
        paths = [
            REPLY / f"{form}_composer.txt",
            REPLY / f"{form}.txt",
            REPLY / f"{form}_claude.txt",
        ]
        text = next((p.read_text() for p in paths if p.exists()), "")
        if not text:
            continue
        preds = parse(text)
        for c in H["cases"]:
            if c["form"] != form and not (form == "SYN_LIVE" and c["form"] == "SYN_LIVE"):
                if c["form"] != form:
                    continue
            pred = preds.get(c["id"], "MISSING")
            ok = pred == c["expect"]
            stop = pred == c.get("company_seal")
            unk = pred.upper() == "UNKNOWN"
            by[form]["n"] += 1
            by[form]["ok"] += int(ok)
            by[form]["company_stop"] += int(stop)
            by[form]["unknown"] += int(unk)
            by[form]["detail"].append(
                {
                    "id": c["id"],
                    "ok": ok,
                    "pred": pred,
                    "expect": c["expect"],
                    "company_stop": stop,
                    "q_clear": c.get("q_clear"),
                }
            )
        by[form]["score"] = f"{by[form]['ok']}/{by[form]['n']}"

    out = {
        "by_form": {k: {kk: vv for kk, vv in v.items() if kk != "detail"} | {"detail": v["detail"]} for k, v in by.items()},
        "summary": {k: v.get("score") for k, v in by.items()},
        "claim": H.get("claim"),
    }
    # slim print
    slim = {
        k: {
            "score": v.get("score"),
            "company_stop": v.get("company_stop"),
            "unknown": v.get("unknown"),
        }
        for k, v in by.items()
    }
    (RESULTS / "synonym_enrich_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(slim, indent=2))


if __name__ == "__main__":
    main()
