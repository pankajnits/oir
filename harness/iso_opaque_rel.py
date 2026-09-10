#!/usr/bin/env python3
"""Split opaque-rel batches into one-quiz-per-file isolation packs.

Kills batch-frequency of shared relation seals (director HMAC reused across items).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "runs" / "wiki_cf_opaque_rel"
OUT = ROOT / "runs" / "wiki_cf_opaque_rel_iso"
ARMS = ("SPAN_NL", "MODEL_PLAN", "LEGEND_NL", "SEAL_PROG", "PLAIN_NL")


def split_batch(text: str) -> tuple[str, list[tuple[str, str]]]:
    parts = re.split(r"(?=##### ID )", text)
    header = parts[0]
    quizzes = []
    for p in parts[1:]:
        m = re.match(r"##### ID (\S+) #####", p)
        if not m:
            continue
        quizzes.append((m.group(1), header + p.strip() + "\n"))
    return header, quizzes


def main():
    n = 0
    index = {}
    for arm in ARMS:
        src = SRC / f"{arm}_ONLY" / "BATCH.txt"
        if not src.exists():
            continue
        _, quizzes = split_batch(src.read_text())
        d = OUT / arm
        d.mkdir(parents=True, exist_ok=True)
        paths = []
        for cid, body in quizzes:
            p = d / f"{cid}.txt"
            p.write_text(body)
            paths.append(str(p))
            n += 1
        index[arm] = paths
        print(arm, len(paths))
    (OUT / "index.json").write_text(__import__("json").dumps({"n_files": n, "arms": index}, indent=2))
    print("wrote", OUT, "files", n)


if __name__ == "__main__":
    main()
