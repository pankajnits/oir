#!/usr/bin/env python3
"""Copy vs bind on dual-path n=32 isolation.

Compare each pred to: gold, trap, last DEMO answer (copy), prompt-local inducer (bind).
Does not read harness gold to *produce* answers; scoring only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from induce_follow_n32_iso import answer_prompt  # noqa: E402
from paths import repo_abs

RESULTS = ROOT / "results"
H = json.loads((RESULTS / "adv_induction_n32_iso_harness.json").read_text())
ANS = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
DEMO_ANS = re.compile(r"^ANSWER_SEALED:\s*(\S+)\s*$", re.I | re.M)


def last_demo_answer(text: str) -> str:
    ms = list(DEMO_ANS.finditer(text.split("--- QUIZ ---")[0]))
    return ms[-1].group(1) if ms else ""


def load_preds(reply_root: Path, arm: str) -> dict[str, str]:
    preds: dict[str, str] = {}
    d = reply_root / arm
    if not d.is_dir():
        return preds
    for p in sorted(d.glob("item_*.txt")):
        preds.update({m.group(1): m.group(2) for m in ANS.finditer(p.read_text())})
    return preds


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "gpt56"
    reply = RESULTS / f"adv_n32_iso_replies_{tag}"
    golds = {c["id"]: c for c in H["cases"]}
    summary, rows = {}, []
    for arm, meta in H["arms"].items():
        preds = load_preds(reply, arm)
        n = copy_n = bind_n = gold_n = trap_n = other = miss = 0
        for i, cid in enumerate(meta["ids"]):
            c = golds[cid]
            pred = preds.get(cid, "")
            n += 1
            if not pred:
                miss += 1
                rows.append({"arm": arm, "id": cid, "pred": "MISSING", "class": "missing"})
                continue
            prompt = repo_abs(meta["item_paths"][i]).read_text()
            _, bind = answer_prompt(prompt)
            copy = last_demo_answer(prompt)
            cls = "other"
            if pred == c["gold"]:
                cls = "gold"
                gold_n += 1
            if c.get("trap") and pred == c["trap"]:
                trap_n += 1
                if cls == "other":
                    cls = "trap"
            if pred == copy:
                copy_n += 1
                if cls == "other":
                    cls = "copy_demo"
            if pred == bind:
                bind_n += 1
                if cls in ("other", "gold"):
                    # gold often equals bind on matched-relation
                    cls = "bind_or_gold" if pred == c["gold"] else "bind"
            if cls == "other":
                other += 1
            rows.append(
                {
                    "arm": arm,
                    "id": cid,
                    "pred": pred,
                    "gold": c["gold"],
                    "bind": bind,
                    "copy": copy,
                    "class": cls,
                }
            )
        summary[arm] = {
            "n": n,
            "gold": f"{gold_n}/{n}",
            "trap": f"{trap_n}/{n}",
            "copy_last_demo": f"{copy_n}/{n}",
            "equiv_inducer": f"{bind_n}/{n}",
            "missing": miss,
        }
    out = {"model": tag, "summary": summary, "rows": rows, "reply_dir": str(reply)}
    path = RESULTS / f"copy_vs_bind_n32_{tag}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
