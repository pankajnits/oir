#!/usr/bin/env python3
"""Prompt-local demo relation induction + follow (no harness gold).

Reads MUT prompt.txt only: majority 2-hop relation seals from DEMOs,
apply on QUIZ; else UNKNOWN. Used as an isolation composer-2.5 baseline.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs

RESULTS = ROOT / "results"
HARNESS = RESULTS / "adv_induction_n32_iso_harness.json"

TRIPLE = re.compile(r"^(E[0-9a-f]+)\s*\|\s*(E[0-9a-f]+)\s*\|\s*(E[0-9a-f]+)\s*$", re.I | re.M)
START_RE = re.compile(r"^START\s+(E[0-9a-f]+)\s*$", re.I | re.M)
ANS_RE = re.compile(r"^ANSWER_SEALED:\s*(E[0-9a-f]+|UNKNOWN)\s*$", re.I | re.M)
ID_RE = re.compile(r"##### ID\s+(\S+)\s+#####")


def parse_triples(block: str) -> list[tuple[str, str, str]]:
    out = []
    for line in block.splitlines():
        m = TRIPLE.match(line.strip())
        if m:
            out.append((m.group(1), m.group(2), m.group(3)))
    return out


def follow(start: str, rels: list[str], triples: list[tuple[str, str, str]]) -> list[str]:
    adj: dict[tuple[str, str], list[str]] = defaultdict(list)
    for h, r, t in triples:
        adj[(h, r)].append(t)
    cur = [start]
    for r in rels:
        nxt = []
        for c in cur:
            nxt.extend(adj.get((c, r), []))
        cur = list(dict.fromkeys(nxt))
        if not cur:
            return []
    return cur


def induce_rels_from_demos(text: str) -> list[str] | None:
    """Find majority 2-hop relation pair used by demos."""
    parts = re.split(r"\nDEMO\s+\d+:\n", text)
    pairs = []
    for part in parts[1:]:
        if "--- QUIZ ---" in part:
            part = part.split("--- QUIZ ---")[0]
        sm = START_RE.search(part)
        am = ANS_RE.search(part)
        if not sm or not am or am.group(1).upper() == "UNKNOWN":
            continue
        start, ans = sm.group(1), am.group(1)
        triples = parse_triples(part)
        # enumerate 2-hop paths start->ans
        # get outgoing rels
        outs = [(r, t) for h, r, t in triples if h == start]
        found = None
        for r1, mid in outs:
            for h, r2, t in triples:
                if h == mid and t == ans:
                    found = (r1, r2)
                    break
            if found:
                break
        if found:
            pairs.append(found)
    if not pairs:
        return None
    (r1, r2), n = Counter(pairs).most_common(1)[0]
    if n < max(1, (len(pairs) + 1) // 2):
        return None
    return [r1, r2]


def answer_prompt(text: str) -> tuple[str, str]:
    cid_m = ID_RE.search(text)
    cid = cid_m.group(1) if cid_m else "UNKNOWN_ID"
    quiz = text.split("--- QUIZ ---")[-1]
    sm = START_RE.search(quiz)
    if not sm:
        return cid, "UNKNOWN"
    start = sm.group(1)
    triples = parse_triples(quiz)
    rels = induce_rels_from_demos(text)
    if not rels:
        return cid, "UNKNOWN"
    outs = follow(start, rels, triples)
    if len(outs) == 1:
        return cid, outs[0]
    return cid, "UNKNOWN"


def main() -> None:
    tag = "auto"
    h = json.loads(HARNESS.read_text())
    reply_root = RESULTS / f"adv_n32_iso_replies_{tag}"
    arms = ["SAME_TRAP", "CROSS_TRAP", "SAME_BALANCED", "CROSS_BALANCED"]
    for arm in arms:
        meta = h["arms"][arm]
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(meta["item_paths"]):
            text = repo_abs(p).read_text()
            cid, pred = answer_prompt(text)
            assert cid == meta["ids"][i], (cid, meta["ids"][i])
            (out_dir / f"item_{i}.txt").write_text(
                f"ANSWER_SEALED[{cid}]: {pred}\n# method: prompt-local demo-rel induction\n"
            )
        print(arm, "wrote", N := len(meta["ids"]))
    print("done", tag)


if __name__ == "__main__":
    main()
