#!/usr/bin/env python3
"""Score isolation 2x2-style replies (ANSWER_PLAIN or ANSWER_SEALED).

  python3 harness/score_factorial_2x2.py gpt56 [harness_stem]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
ANS_PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*([^\n]+)", re.I)
ANS_SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", s).lower()


def load_preds(reply_root: Path, arm: str, *, sealed: bool) -> dict[str, str]:
    preds: dict[str, str] = {}
    d = reply_root / arm
    if not d.is_dir():
        return preds
    rx = ANS_SEAL if sealed else ANS_PLAIN
    for p in sorted(d.glob("item_*.txt")):
        text = p.read_text()
        for m in rx.finditer(text):
            preds[m.group(1)] = m.group(2).strip()
    return preds


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "gpt56"
    stem = sys.argv[2] if len(sys.argv) > 2 else "factorial_2x2_iso_harness"
    H = json.loads((RESULTS / f"{stem}.json").read_text())
    reply = RESULTS / f"{stem}_replies_{tag}"
    gold_by_id = {}
    for c in H["cases"]:
        for arm, cid in c["ids"].items():
            gold_by_id[cid] = c["gold"]
    summary, rows = {}, []
    for arm, meta in H["arms"].items():
        sealed = bool(meta.get("sealed_answer"))
        preds = load_preds(reply, arm, sealed=sealed)
        ok = unk = miss = decoy = 0
        for cid in meta["ids"]:
            case = next(c for c in H["cases"] if c["ids"][arm] == cid)
            gold = case.get("golds", {}).get(arm) or gold_by_id[cid]
            decoy_tok = case.get("decoys", {}).get(arm) or case.get("decoy_hq") or ""
            pred = preds.get(cid, "")
            if not pred:
                miss += 1
            if pred.upper() == "UNKNOWN":
                unk += 1
            hit = bool(pred) and pred.upper() != "UNKNOWN" and (
                pred == gold or (not sealed and norm(pred) == norm(gold))
            )
            ok += int(hit)
            if pred and not hit and decoy_tok and (
                pred == decoy_tok or (not sealed and norm(pred) == norm(decoy_tok))
            ):
                decoy += 1
            rows.append(
                {
                    "arm": arm,
                    "id": cid,
                    "gold": gold,
                    "pred": pred or "MISSING",
                    "ok": hit,
                }
            )
        n = len(meta["ids"])
        summary[arm] = {
            "score": f"{ok}/{n}",
            "unknown": unk,
            "missing": miss,
            "decoy": decoy,
        }
    out = {
        "model": tag,
        "n": H["n"],
        "protocol": "isolation",
        "start_in_question": True,
        "source": H["source"],
        "summary": summary,
        "rows": rows,
        "reply_dir": str(reply.relative_to(ROOT)) if reply.is_relative_to(ROOT) else str(reply),
    }
    out_name = stem.replace("_harness", "") + f"_{tag}.json"
    path = RESULTS / out_name
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
