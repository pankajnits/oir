#!/usr/bin/env python3
"""Score isolation 2x2-style replies (ANSWER_PLAIN or ANSWER_SEALED).

  python3 harness/score_factorial_2x2.py TAG [harness_stem] [--force]

Refuses to overwrite an existing score JSON unless ``--force``. An arm with
every item missing is ``n.r.``, never ``0/n``. Empty completions stored as
``NO_OUTPUT`` are counted separately and are not ``UNKNOWN``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from lockjson import write_lock  # noqa: E402
from reply_parse import ANS_PLAIN, ANS_SEAL, NO_OUTPUT, preds_from_text  # noqa: E402

RESULTS = ROOT / "results"


def norm(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", s).lower()


def load_preds(reply_root: Path, arm: str, *, sealed: bool) -> dict[str, str]:
    preds: dict[str, str] = {}
    d = reply_root / arm
    if not d.is_dir():
        return preds
    rx = ANS_SEAL if sealed else ANS_PLAIN
    for p in sorted(d.glob("item_*.txt")):
        preds.update(preds_from_text(p.read_text(), rx))
    return preds


def score(tag: str, stem: str = "factorial_2x2_iso_harness", *, force: bool = False,
          results_dir: Path = RESULTS) -> dict:
    H = json.loads((results_dir / f"{stem}.json").read_text())
    reply = results_dir / f"{stem}_replies_{tag}"
    gold_by_id = {}
    for c in H["cases"]:
        for arm, cid in c["ids"].items():
            gold_by_id[cid] = c["gold"]
    summary, rows = {}, []
    for arm, meta in H["arms"].items():
        sealed = bool(meta.get("sealed_answer"))
        preds = load_preds(reply, arm, sealed=sealed)
        ok = unk = miss = decoy = nout = 0
        for cid in meta["ids"]:
            case = next(c for c in H["cases"] if c["ids"][arm] == cid)
            gold = case.get("golds", {}).get(arm) or gold_by_id[cid]
            decoy_tok = case.get("decoys", {}).get(arm) or case.get("decoy_hq") or ""
            pred = preds.get(cid, "")
            if not pred:
                miss += 1
            elif pred.upper() == NO_OUTPUT:
                nout += 1
            if pred.upper() == "UNKNOWN":
                unk += 1
            hit = bool(pred) and pred.upper() not in {"UNKNOWN", NO_OUTPUT} and (
                pred == gold or (not sealed and norm(pred) == norm(gold))
            )
            ok += int(hit)
            if pred and not hit and decoy_tok and pred.upper() != NO_OUTPUT and (
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
        cell = {
            "score": "n.r." if miss == n else f"{ok}/{n}",
            "unknown": unk,
            "missing": miss,
            "decoy": decoy,
        }
        if nout:
            cell["no_output"] = nout
        summary[arm] = cell
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
    path = results_dir / out_name
    write_lock(path, out, force=force)
    print(json.dumps(summary, indent=2))
    print("wrote", path)
    return out


def main() -> None:
    force = "--force" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--force"]
    if not argv:
        raise SystemExit("usage: score_factorial_2x2.py TAG [harness_stem] [--force]")
    tag = argv[0]
    stem = argv[1] if len(argv) > 1 else "factorial_2x2_iso_harness"
    score(tag, stem, force=force)


if __name__ == "__main__":
    main()
