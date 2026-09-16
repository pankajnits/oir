#!/usr/bin/env python3
"""Unique-path, hashed ids, no ARM line.

Same HMAC CONTEXT as Wiki-H5 OPAQUE_UNIQUE. Does not rewrite factorial prompts.

  python3 harness/unique_no_arm_iso.py build
  python3 harness/run_openai_iso_harness.py results/unique_no_arm_iso_harness.json gpt56uninone \\
      --model gpt-5.6-sol --max-completion-tokens 512
  python3 harness/run_openai_iso_harness.py results/unique_no_arm_iso_n200_harness.json gpt56n200uninone \\
      --model gpt-5.6-sol --max-completion-tokens 512 --workers 8
  python3 harness/score_factorial_2x2.py gpt56uninone unique_no_arm_iso_harness
  python3 harness/score_factorial_2x2.py gpt56n200uninone unique_no_arm_iso_n200_harness
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from factorial_2x2_iso import (  # noqa: E402
    item_key as n32_item_key,
    pack,
    render,
    two_hops,
    unique_edges,
)
from oir import EntitySeal  # noqa: E402
from paths import repo_rel  # noqa: E402

RESULTS = ROOT / "results"
CID_SALT = b"oir-unique-no-arm-v1"
N200_KEY = b"oir-fact-2x2-iso-n200-v1"
ARM = "OPQ_NONE_UNI"


def n200_item_key(i: int) -> bytes:
    return hashlib.sha256(N200_KEY + str(i).encode()).digest()[:16]


def cid_for(stem: str, i: int) -> str:
    return "UNA_" + hashlib.sha256(CID_SALT + stem.encode() + b":" + str(i).encode()).hexdigest()[:10]


def ctx_of(prompt: str) -> str:
    return prompt.split("CONTEXT:\n", 1)[1]


def build_one(*, stem: str, src_harness: Path, key_fn, named_unique_root: Path, n: int) -> dict:
    src = json.loads(src_harness.read_text())
    assert src["n"] == n
    cases_src = src["cases"]
    runs = ROOT / "runs" / stem
    if runs.exists():
        for p in runs.rglob("prompt.txt"):
            p.unlink()
    runs.mkdir(parents=True, exist_ok=True)
    ids, paths, cases = [], [], []
    for i, row in enumerate(cases_src):
        decoy = cases_src[(i + 1) % n]
        edges = unique_edges(row, decoy)
        EntitySeal.assert_raw_injective(x for e in edges for x in e)
        hops = two_hops(edges, row["person"])
        assert len(hops) == 1 and hops[0][2] == row["gold"], hops
        sealer = EntitySeal(key_fn(i))
        ctx = render(edges, sealer)
        named = (named_unique_root / f"item_{i}" / "prompt.txt").read_text()
        assert ctx_of(named).rstrip("\n") == ctx.rstrip("\n"), i
        assert "one 2-hop from start" in named
        cid = cid_for(stem, i)
        path = runs / ARM / f"item_{i}" / "prompt.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        q = f"What city is the headquarters of the company led by {row['person']}?"
        body = pack(cid, q, ctx, sealed_ans=False, extra=None)
        assert "ARM " not in body
        assert "OPAQUE_UNIQUE" not in body
        path.write_text(body)
        ids.append(cid)
        paths.append(repo_rel(path))
        cases.append(
            {
                "i": i,
                "person": row["person"],
                "company": row["company"],
                "gold": row["gold"],
                "decoy_hq": decoy["gold"],
                "ids": {ARM: cid},
            }
        )
    harness = {
        "n": n,
        "protocol": "isolation",
        "suite": stem,
        "source": src["source"],
        "keys": src.get("keys"),
        "start_in_question": True,
        "note": (
            "Unique-path opaque graphs; hashed ids; no ARM. Same HMAC CONTEXT as "
            "OPAQUE_UNIQUE. Does not rewrite factorial prompts or scores."
        ),
        "arms": {ARM: {"ids": ids, "item_paths": paths}},
        "cases": cases,
    }
    out = RESULTS / f"{stem}_harness.json"
    out.write_text(json.dumps(harness, indent=2, ensure_ascii=False) + "\n")
    print("wrote", out, "n", n)
    return harness


def build() -> None:
    build_one(
        stem="unique_no_arm_iso",
        src_harness=RESULTS / "factorial_2x2_iso_harness.json",
        key_fn=n32_item_key,
        named_unique_root=ROOT / "runs/factorial_2x2_iso/OPAQUE_UNIQUE",
        n=32,
    )
    build_one(
        stem="unique_no_arm_iso_n200",
        src_harness=RESULTS / "factorial_2x2_iso_n200_harness.json",
        key_fn=n200_item_key,
        named_unique_root=ROOT / "runs/factorial_2x2_iso_n200/OPAQUE_UNIQUE",
        n=200,
    )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd != "build":
        raise SystemExit("usage: unique_no_arm_iso.py build")
    build()
