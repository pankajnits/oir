#!/usr/bin/env python3
"""Score isolation three-arm n=32 replies."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "ceiling_three_arm_n32_iso_harness.json").read_text())
ANS_SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ANS_PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*([^\n]+)", re.I)


def load_preds(reply_root: Path, arm: str) -> dict[str, str]:
    preds: dict[str, str] = {}
    d = reply_root / arm
    if not d.is_dir():
        return preds
    for p in sorted(d.glob("item_*.txt")):
        text = p.read_text()
        if arm == "PLAIN_PROG":
            preds.update({m.group(1): m.group(2).strip() for m in ANS_PLAIN.finditer(text)})
        else:
            preds.update({m.group(1): m.group(2).strip() for m in ANS_SEAL.finditer(text)})
    return preds


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "gpt56"
    reply = RESULTS / f"ceiling_n32_iso_replies_{tag}"
    gold_by = {c["id_plain"]: c | {"gold": c["expect_plain"], "arm": "PLAIN_PROG"} for c in H["cases"]}
    gold_by.update({c["id_sealprog"]: c | {"gold": c["expect_seal"], "arm": "SEAL_PROG"} for c in H["cases"]})
    gold_by.update({c["id_sealnl"]: c | {"gold": c["expect_seal"], "arm": "SEAL_NL"} for c in H["cases"]})
    summary, rows = {}, []
    for arm, meta in H["arms"].items():
        preds = load_preds(reply, arm)
        ok = company_stop = unk = miss = 0
        for cid in meta["ids"]:
            c = gold_by[cid]
            pred = preds.get(cid, "")
            if not pred:
                miss += 1
            if pred.upper() == "UNKNOWN":
                unk += 1
            hit = pred == c["gold"] if arm == "PLAIN_PROG" else pred == c["expect_seal"]
            cstop = arm == "SEAL_NL" and pred == c["company_seal"]
            ok += int(hit)
            company_stop += int(cstop)
            rows.append({"arm": arm, "id": cid, "gold": c["gold"] if arm == "PLAIN_PROG" else c["expect_seal"], "pred": pred or "MISSING", "ok": hit, "company_stop": cstop})
        n = len(meta["ids"])
        summary[arm] = {"score": f"{ok}/{n}", "unknown": unk, "missing": miss, "company_stop": f"{company_stop}/{n}"}
    out = {
        "model": tag,
        "n": H["n"],
        "protocol": "isolation",
        "keys": H.get("keys"),
        "summary": summary,
        "rows": rows,
        "reply_dir": str(reply),
    }
    path = RESULTS / f"ceiling_three_arm_n32_iso_{tag}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
