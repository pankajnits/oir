#!/usr/bin/env python3
"""WikiMovies people 2×2 at n=100. Does not overwrite the n=32 freeze."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from paths import repo_rel
from factorial_2x2_iso import two_hops as hops  # type: ignore
from metaqa_2x2_iso import (  # type: ignore
    ARMS,
    KB,
    ambig_edges,
    candidates,
    pack,
    parse_kb,
    render,
    unique_edges,
)
from oir import EntitySeal, path_program

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "metaqa_2x2_people_n100_iso"
FREEZE32 = ROOT / "data" / "metaqa" / "oir_2hop_people_n32.json"
FREEZE = ROOT / "data" / "metaqa" / "oir_2hop_people_n100.json"
SEED = 20260824
N = 100
KEY_BASE = b"oir-metaqa-2x2-people-n100-v1"


def item_key(i: int) -> bytes:
    return hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:16]


def build() -> dict:
    if not KB.exists():
        raise SystemExit(f"Download WikiMovies KB to {KB}")
    movies = parse_kb(KB)
    pool = candidates(movies)
    keep_raw = json.loads(FREEZE32.read_text())["items"]
    keep, seen_act = [], set()
    for r in keep_raw:
        if r["actor"] in seen_act:
            continue
        keep.append(r)
        seen_act.add(r["actor"])
    seen_am = {(r["actor"], r["movie"]) for r in keep}
    extra = [
        r
        for r in pool
        if (r["actor"], r["movie"]) not in seen_am and r["actor"] not in seen_act
    ]
    extra_u, extra_act = [], set()
    rng = random.Random(SEED)
    rng.shuffle(extra)
    for r in extra:
        if r["actor"] in extra_act:
            continue
        extra_u.append(r)
        extra_act.add(r["actor"])
    need = N - len(keep)
    if need > len(extra_u):
        raise SystemExit(f"need {need} extra unique actors, have {len(extra_u)} keep={len(keep)}")
    picked = keep + extra_u[:need]
    assert len({r["actor"] for r in picked}) == N, len({r["actor"] for r in picked})
    FREEZE.write_text(json.dumps({"seed": SEED, "n": N, "items": picked}, indent=2))
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)
    arms = {a: {"ids": [], "item_paths": []} for a in ARMS}
    cases = []
    for i, row in enumerate(picked):
        decoy = next(
            picked[(i + k) % N]
            for k in range(1, N)
            if picked[(i + k) % N]["actor"] != row["actor"]
            and picked[(i + k) % N]["movie"] != row["movie"]
        )
        u_edges = unique_edges(row, decoy)
        a_edges = list(dict.fromkeys(ambig_edges(row, decoy)))
        assert len(hops(u_edges, row["actor"])) == 1
        assert len(hops(a_edges, row["actor"])) == 2
        sealer = EntitySeal(item_key(i))
        q = f"Who directed a movie that {row['actor']} starred in?"
        plan = path_program(
            row["actor"],
            (sealer.atom("starred_in"), sealer.atom("directed_by")),
            row["director"],
        )
        specs = {
            "ENG_UNIQUE": (q, render(u_edges, None), "ARM ENG_UNIQUE n=100"),
            "ENG_AMBIG": (q, render(a_edges, None), "ARM ENG_AMBIG n=100"),
            "OPAQUE_UNIQUE": (q, render(u_edges, sealer), "ARM OPAQUE_UNIQUE n=100"),
            "OPAQUE_AMBIG": (q, render(a_edges, sealer), "ARM OPAQUE_AMBIG n=100"),
            "OPAQUE_AMBIG_PLAN": (
                q + "\n\n" + plan.body,
                render(a_edges, sealer),
                "ARM OPAQUE_AMBIG_PLAN n=100",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"MQA100_{arm}_{i}"
            ids[arm] = cid
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, qq, ctx, header))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append(
            {
                "i": i,
                **row,
                "ids": ids,
                "gold": row["director"],
                "decoy_hq": row["writer"],
            }
        )
    harness = {
        "n": N,
        "seed": SEED,
        "protocol": "isolation",
        "source": "WikiMovies kb; n=100 includes the n=32 freeze plus 68 new rows",
        "source_url": "https://github.com/rohit129/Movie_KnowledgeGraph_QA/blob/master/wiki_entities_kb.txt",
        "freeze": str(FREEZE.relative_to(ROOT)),
        "start_in_question": True,
        "keys": "per-item HMAC on relation atoms only",
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "metaqa_2x2_people_n100_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print("wrote", out, "n", N)
    return harness


if __name__ == "__main__":
    build()
