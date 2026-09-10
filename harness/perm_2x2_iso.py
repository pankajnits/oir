#!/usr/bin/env python3
"""HMAC vs random permutation on the same Wikidata 2×2 graphs.

Same 32 CEOs / edges as factorial_2x2_iso.py. Relation labels are renamed with
a per-item random injection into E+12hex tokens (HMAC-shaped, not keyed HMAC).
Entities stay English; start string in q.
"""
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
from factorial_2x2_iso import (  # type: ignore
    N,
    SEED,
    SOURCE,
    ambig_edges,
    pack,
    two_hops,
    unique_edges,
)
from oir import EntitySeal, SealRouter, path_program
from oir.adapters import load_json_records

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "perm_2x2_iso"
KEY_BASE = b"oir-perm-2x2-iso-v1"
ARMS = ["PERM_UNIQUE", "PERM_AMBIG", "PERM_AMBIG_PLAN"]


class PermSeal:
    """Injective random renaming; tokens look like EntitySeal (E+12 hex)."""

    def __init__(self, rng: random.Random, nbytes: int = 6):
        self.rng = rng
        self.nbytes = nbytes
        self.fwd: dict[str, str] = {}
        self.used: set[str] = set()

    def atom(self, a: str) -> str:
        a = EntitySeal.normalize(a)
        if a not in self.fwd:
            while True:
                tok = "E" + bytes(self.rng.randrange(256) for _ in range(self.nbytes)).hex()
                if tok not in self.used:
                    break
            self.fwd[a] = tok
            self.used.add(tok)
        return self.fwd[a]


def item_rng(i: int) -> random.Random:
    seed = int.from_bytes(hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:8], "big")
    return random.Random(seed)


def render(edges, sealer: PermSeal) -> str:
    return SealRouter([(h, sealer.atom(r), t) for h, r, t in edges]).render()


def picked_rows() -> list[dict]:
    recs = load_json_records(SOURCE)
    rng = random.Random(SEED)
    pool = [r for r in recs if r["hq"] and r["person"] and r["company"]]
    return rng.sample(pool, N)


def build() -> dict:
    picked = picked_rows()
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)
    arms = {a: {"ids": [], "item_paths": []} for a in ARMS}
    cases = []
    for i, row in enumerate(picked):
        decoy = picked[(i + 1) % N]
        if decoy["hq"] == row["hq"] or decoy["person"] == row["person"]:
            decoy = {
                "person": f"DecoyPerson_{i}",
                "company": f"DecoyCo_{i}",
                "hq": f"DecoyCity_{i}",
            }
        u_edges = unique_edges(row, decoy)
        a_edges = ambig_edges(row, decoy)
        assert len(two_hops(u_edges, row["person"])) == 1
        assert len(two_hops(a_edges, row["person"])) == 2
        sealer = PermSeal(item_rng(i))
        q = (
            "What city is the headquarters of the company led by "
            f"{row['person']}?"
        )
        plan = path_program(
            row["person"],
            (sealer.atom("works_at"), sealer.atom("headquartered_in")),
            row["hq"],
        )
        router = SealRouter([(h, sealer.atom(r), t) for h, r, t in a_edges])
        assert router.path(
            row["person"], [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        ) == [row["hq"]]
        specs = {
            "PERM_UNIQUE": (
                q,
                render(u_edges, sealer),
                "ARM PERM_UNIQUE: random permutation of relation labels; one 2-hop.",
            ),
            "PERM_AMBIG": (
                q,
                render(a_edges, sealer),
                "ARM PERM_AMBIG: random permutation of relation labels; two 2-hops.",
            ),
            "PERM_AMBIG_PLAN": (
                q + "\n\n" + plan.body,
                render(a_edges, sealer),
                "ARM PERM_AMBIG_PLAN: same permutation graph plus explicit relation sequence.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"PERM_{arm}_{i}"
            ids[arm] = cid
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, qq, ctx, sealed_ans=False, extra=header))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append(
            {
                "i": i,
                "person": row["person"],
                "ids": ids,
                "gold": row["hq"],
                "decoy_hq": decoy["hq"],
            }
        )
    harness = {
        "n": N,
        "seed": SEED,
        "protocol": "isolation",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_public": "Same Wikidata CEO 2x2 graphs; relation map is a random injection, not HMAC",
        "keys": "per-item RNG permutation into E+12hex; entities English",
        "start_in_question": True,
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "perm_2x2_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print("wrote", out)
    return harness


if __name__ == "__main__":
    build()
