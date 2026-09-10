#!/usr/bin/env python3
"""Score WTQFIX NL vs DSL replies."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLY = RESULTS / "wtq_dsl_replies"
H = json.loads((RESULTS / "wtq_dsl_harness.json").read_text())


def parse(text: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(
        r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", text, flags=re.I
    ):
        out[m.group(1)] = m.group(2).strip()
    return out


def main():
    by_form = defaultdict(lambda: {"ok": 0, "n": 0, "detail": []})
    for form, stem in [("NL", "WTQFIX_NL"), ("DSL", "WTQFIX_DSL")]:
        paths = [
            REPLY / f"{stem}_composer.txt",
            REPLY / f"{stem}.txt",
            REPLY / f"{stem}_claude.txt",
        ]
        text = ""
        used = None
        for p in paths:
            if p.exists():
                text = p.read_text()
                used = str(p)
                break
        if not text:
            print(f"MISSING reply for {form}")
            continue
        preds = parse(text)
        model = "claude" if used and "claude" in used else "composer"
        for c in H["cases"]:
            if c["form"] != form:
                continue
            pred = preds.get(c["id"], "MISSING")
            ok = pred == c["expect"]
            by_form[form]["n"] += 1
            by_form[form]["ok"] += int(ok)
            by_form[form]["detail"].append(
                {
                    "id": c["id"],
                    "ok": ok,
                    "pred": pred,
                    "expect": c["expect"],
                    "stratum": c["stratum"],
                    "in_ctx": c.get("in_ctx"),
                    "model": model,
                }
            )
        by_form[form]["score"] = f"{by_form[form]['ok']}/{by_form[form]['n']}"
        by_form[form]["reply"] = used

    out = {
        "by_form": dict(by_form),
        "claim": H.get("claim"),
        "note": (
            "DSL uses gold-aligned ROW/COL LOOKUP (execution under opacity). "
            "Not NL→SQL compilation. Parallel to PATH_PROG saturation."
        ),
    }
    (RESULTS / "wtq_dsl_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v.get("score") for k, v in by_form.items()}, indent=2))


if __name__ == "__main__":
    main()
