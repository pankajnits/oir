#!/usr/bin/env python3
"""Third opaque-token scheme: random alphanumeric labels, not HMAC-shaped.

Same 32 Wikidata CEO graphs as factorial_2x2_iso.py / perm_2x2_iso.py.
Entities stay English; start string in q. Tokens are 12-char [a-z0-9] and
are rejected if they match E+12hex (the HMAC/permutation shape).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import string
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
from oir import SealRouter
from oir.adapters import load_json_records

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "alpha_2x2_iso"
KEY_BASE = b"oir-alpha-2x2-iso-v1"
ARMS = ["ALPHA_UNIQUE", "ALPHA_AMBIG"]
HMAC_SHAPE = re.compile(r"^E[0-9a-f]{12}$")
ALPHABET = string.ascii_lowercase + string.digits


class AlphaSeal:
    """Injective random alphanumeric renaming; not HMAC-shaped."""

    def __init__(self, rng: random.Random, nchars: int = 12):
        self.rng = rng
        self.nchars = nchars
        self.fwd: dict[str, str] = {}
        self.used: set[str] = set()

    def atom(self, a: str) -> str:
        from oir import EntitySeal

        a = EntitySeal.normalize(a)
        if a not in self.fwd:
            while True:
                tok = "".join(self.rng.choice(ALPHABET) for _ in range(self.nchars))
                if HMAC_SHAPE.match(tok) or tok in self.used:
                    continue
                break
            self.fwd[a] = tok
            self.used.add(tok)
        return self.fwd[a]


def item_rng(i: int) -> random.Random:
    seed = int.from_bytes(hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:8], "big")
    return random.Random(seed)


def render(edges, sealer: AlphaSeal) -> str:
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
        sealer = AlphaSeal(item_rng(i))
        for rel in ("works_at", "headquartered_in", "partner_of", "located_in"):
            assert not HMAC_SHAPE.match(sealer.atom(rel))
        q = (
            "What city is the headquarters of the company led by "
            f"{row['person']}?"
        )
        router = SealRouter([(h, sealer.atom(r), t) for h, r, t in a_edges])
        assert router.path(
            row["person"], [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        ) == [row["hq"]]
        specs = {
            "ALPHA_UNIQUE": (
                q,
                render(u_edges, sealer),
                "ARM ALPHA_UNIQUE: random alphanumeric relation labels; one 2-hop.",
            ),
            "ALPHA_AMBIG": (
                q,
                render(a_edges, sealer),
                "ARM ALPHA_AMBIG: random alphanumeric relation labels; two 2-hops.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"ALPHA_{arm}_{i}"
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
        "source_public": "Same Wikidata CEO 2x2 graphs; relation map is random alphanumeric, not HMAC",
        "keys": "per-item RNG alphanumeric tokens; entities English; not E+12hex",
        "start_in_question": True,
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "alpha_2x2_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2) + "\n")
    print("wrote", out)
    return harness


if __name__ == "__main__":
    build()
