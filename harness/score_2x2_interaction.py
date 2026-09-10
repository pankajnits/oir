#!/usr/bin/env python3
"""Item-level opacity x ambiguity contrast on locked factorial JSON.

For each of 32 items:
  d_unique = 1[opaque unique] - 1[English unique]
  d_two    = 1[opaque two-path] - 1[English two-path]
  c_i      = d_two - d_unique

T = sum c_i is the difference-in-differences in exact-match counts.

Null: unique-path and two-path opacity effects are exchangeable (sign-flip
c_i independently). Quasi-complete separation makes a logistic GLM a poor
default; this is the interaction test reported in the paper.

Usage: python3 harness/score_2x2_interaction.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON = ROOT / "results" / "factorial_2x2_iso_gpt56.json"
NEED = ("ENG_UNIQUE", "ENG_AMBIG", "OPAQUE_UNIQUE", "OPAQUE_AMBIG")


def item_rows(path: Path) -> dict[int, dict[str, bool]]:
    data = json.loads(path.read_text())
    by: dict[int, dict[str, bool]] = defaultdict(dict)
    for row in data["rows"]:
        idx = int(str(row["id"]).rsplit("_", 1)[-1])
        by[idx][row["arm"]] = bool(row["ok"])
    for i in range(32):
        missing = [k for k in NEED if k not in by[i]]
        if missing:
            raise SystemExit(f"item {i} missing {missing}")
    return by


def contrasts(by: dict[int, dict[str, bool]]) -> list[int]:
    out = []
    for i in range(32):
        du = int(by[i]["OPAQUE_UNIQUE"]) - int(by[i]["ENG_UNIQUE"])
        da = int(by[i]["OPAQUE_AMBIG"]) - int(by[i]["ENG_AMBIG"])
        out.append(da - du)
    return out


def main() -> None:
    by = item_rows(JSON)
    c = contrasts(by)
    T = sum(c)
    nz = sum(1 for x in c if x != 0)
    # Two-sided exact p: only all-flip and none-flip of nonzero items reach |T|.
    p_exact = 2 / (2**nz) if nz else 1.0
    b = c_mc = 0
    for i in range(32):
        e, o = by[i]["ENG_AMBIG"], by[i]["OPAQUE_AMBIG"]
        if e and not o:
            b += 1
        if o and not e:
            c_mc += 1
    hist = Counter(c)
    print(f"source\t{JSON}")
    print(f"DiD_sum\t{T}/32")
    print(f"contrast_hist\t{dict(sorted(hist.items()))}")
    print(f"nonzero_items\t{nz}")
    print(f"sign_flip_two_sided_p\t{p_exact:.6e}\t(2/2^{nz})")
    print(f"McNemar_two_path\t{b}\tvs\t{c_mc}")


if __name__ == "__main__":
    main()
