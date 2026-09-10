#!/usr/bin/env python3
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLY = RESULTS / "planner_local_replies"
H = json.loads((RESULTS / "planner_local_harness.json").read_text())


def parse(text):
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", text, flags=re.I)
    }


def main():
    by = defaultdict(lambda: {"ok": 0, "n": 0, "company_stop": 0, "unknown": 0, "detail": []})
    for form in ["RAW_NL", "CTX_ALIAS", "DET_PROG", "LOCAL_PROG"]:
        paths = [REPLY / f"{form}_composer.txt", REPLY / f"{form}.txt"]
        text = next((p.read_text() for p in paths if p.exists()), "")
        if not text:
            print("MISSING", form)
            continue
        preds = parse(text)
        for c in H["cases"]:
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
                {"id": c["id"], "ok": ok, "pred": pred, "expect": c["expect"], "company_stop": stop}
            )
        by[form]["score"] = f"{by[form]['ok']}/{by[form]['n']}"
    out = {
        "by_form": dict(by),
        "summary": {k: v.get("score") for k, v in by.items()},
        "local_planner": {
            m: {
                "compile": H["local_planner"][m]["compile_acc"],
                "router": H["local_planner"][m]["router_acc"],
            }
            for m in H["local_planner"]
        },
        "det_router": H["router_scores"],
        "claim": H.get("claim"),
    }
    (RESULTS / "planner_local_results.json").write_text(json.dumps(out, indent=2))
    print(
        json.dumps(
            {"summary": out["summary"], "local": out["local_planner"], "det": out["det_router"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
