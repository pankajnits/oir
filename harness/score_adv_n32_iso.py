#!/usr/bin/env python3
"""Score adv_induction_n32_iso replies.

Free-form locks: gpt56 / grok45ff / composer25ff.
Tag auto is composer-2.5 and may omit PATH_TRAP; do not cite missing==n as 0/n.

    python3 harness/score_adv_n32_iso.py TAG [--force]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from lockjson import write_lock  # noqa: E402
from reply_parse import ANS_SEAL, preds_from_text  # noqa: E402

RESULTS = ROOT / "results"
H = json.loads((RESULTS / "adv_induction_n32_iso_harness.json").read_text())


def cell_score(k: int, n: int, missing: int) -> str:
    """Print not_run when every item is missing. Do not cite missing==n as 0/n."""
    if n > 0 and missing >= n:
        return "not_run"
    return f"{k}/{n}"


def load_preds(reply_root: Path, arm: str) -> dict[str, str]:
    preds: dict[str, str] = {}
    d = reply_root / arm
    if d.is_dir():
        for p in sorted(d.glob("item_*.txt")):
            preds.update(preds_from_text(p.read_text(), ANS_SEAL))
    return preds


def main() -> None:
    force = "--force" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--force"]
    if not argv:
        raise SystemExit("usage: score_adv_n32_iso.py TAG [--force]")
    model = argv[0]
    reply = RESULTS / f"adv_n32_iso_replies_{model}"
    golds = {c["id"]: c for c in H["cases"]}
    summary, rows = {}, []
    for arm, meta in H["arms"].items():
        preds = load_preds(reply, arm)
        oks, traps = [], []
        unk = miss = 0
        for cid in meta["ids"]:
            c = golds[cid]
            pred = preds.get(cid, "")
            if not pred:
                miss += 1
            if pred.upper() == "UNKNOWN":
                unk += 1
            ok = pred == c["gold"]
            th = bool(c.get("trap")) and pred == c["trap"]
            oks.append(ok)
            traps.append(th)
            rows.append(
                {
                    "arm": arm,
                    "id": cid,
                    "gold": c["gold"],
                    "pred": pred or "MISSING",
                    "ok": ok,
                    "chose_trap": th,
                }
            )
        n = len(meta["ids"])
        summary[arm] = {
            "score": cell_score(sum(oks), n, miss),
            "trap_rate": cell_score(sum(traps), n, miss),
            "unknown": unk,
            "missing": miss,
        }
    out = {
        "model": model,
        "n": H["n"],
        "protocol": "isolation",
        "summary": summary,
        "rows": rows,
        "reply_dir": str(reply.relative_to(ROOT)) if reply.is_relative_to(ROOT) else str(reply),
    }
    path = RESULTS / f"adv_induction_n32_iso_{model}.json"
    write_lock(path, out, force=force)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("wrote", path)


if __name__ == "__main__":
    main()
