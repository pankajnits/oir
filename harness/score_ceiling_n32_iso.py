#!/usr/bin/env python3
"""Score isolation three-arm n=32 replies.

  python3 harness/score_ceiling_n32_iso.py TAG [--force]

August locks live under ``ceiling_n32_iso_replies_{gpt56,composer25,grok45}``.
Those tags always read that tree. A new tag uses whichever populated tree
has more item files; an empty harness-stem directory cannot shadow a lock.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from lockjson import write_lock  # noqa: E402
from reply_parse import ANS_PLAIN, ANS_SEAL, preds_from_text  # noqa: E402

RESULTS = ROOT / "results"
H = json.loads((RESULTS / "ceiling_three_arm_n32_iso_harness.json").read_text())
LOCKED_TAGS = frozenset({"gpt56", "composer25", "grok45"})
STEM = "ceiling_three_arm_n32_iso_harness_replies_{tag}"
LEGACY = "ceiling_n32_iso_replies_{tag}"


def _n_items(root: Path) -> int:
    return sum(1 for _ in root.glob("*/item_*.txt")) if root.is_dir() else 0


def reply_root(tag: str, results_dir: Path = RESULTS) -> Path:
    """Lock tags always use the short August tree. New tags use populated files."""
    legacy = results_dir / LEGACY.format(tag=tag)
    stem = results_dir / STEM.format(tag=tag)
    if tag in LOCKED_TAGS:
        return legacy
    scored = [(n, p) for p in (stem, legacy) if (n := _n_items(p)) > 0]
    if not scored:
        return stem
    return max(scored, key=lambda x: x[0])[1]


def load_preds(reply_root_dir: Path, arm: str) -> dict[str, str]:
    preds: dict[str, str] = {}
    d = reply_root_dir / arm
    if not d.is_dir():
        return preds
    rx = ANS_PLAIN if arm == "PLAIN_PROG" else ANS_SEAL
    for p in sorted(d.glob("item_*.txt")):
        preds.update(preds_from_text(p.read_text(), rx))
    return preds


def score(tag: str, *, force: bool = False, results_dir: Path = RESULTS) -> dict:
    h = json.loads((results_dir / "ceiling_three_arm_n32_iso_harness.json").read_text())
    reply = reply_root(tag, results_dir)
    gold_by = {c["id_plain"]: c | {"gold": c["expect_plain"], "arm": "PLAIN_PROG"} for c in h["cases"]}
    gold_by.update({c["id_sealprog"]: c | {"gold": c["expect_seal"], "arm": "SEAL_PROG"} for c in h["cases"]})
    gold_by.update({c["id_sealnl"]: c | {"gold": c["expect_seal"], "arm": "SEAL_NL"} for c in h["cases"]})
    summary, rows = {}, []
    for arm, meta in h["arms"].items():
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
        summary[arm] = {
            "score": "n.r." if miss == n else f"{ok}/{n}",
            "unknown": unk,
            "missing": miss,
            "company_stop": "n.r." if miss == n else f"{company_stop}/{n}",
        }
    out = {
        "model": tag,
        "n": h["n"],
        "protocol": "isolation",
        "keys": h.get("keys"),
        "summary": summary,
        "rows": rows,
        "reply_dir": str(reply.relative_to(ROOT) if reply.is_relative_to(ROOT) else reply),
    }
    path = results_dir / f"ceiling_three_arm_n32_iso_{tag}.json"
    write_lock(path, out, force=force)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("wrote", path)
    return out


def main() -> None:
    force = "--force" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--force"]
    if not argv:
        raise SystemExit("usage: score_ceiling_n32_iso.py TAG [--force]")
    score(argv[0], force=force)


if __name__ == "__main__":
    main()
