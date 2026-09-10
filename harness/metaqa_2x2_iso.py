#!/usr/bin/env python3
"""OIR 2x2 on the public WikiMovies KB (MetaQA's movie graph).

Upstream: https://github.com/rohit129/Movie_KnowledgeGraph_QA/blob/master/wiki_entities_kb.txt
(WikiMovies / MetaQA movie triples). Start entity is always in the question.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program
from paths import repo_rel

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "metaqa_2x2_people_iso"
KB = ROOT / "data" / "metaqa" / "wiki_entities_kb.txt"
FREEZE = ROOT / "data" / "metaqa" / "oir_2hop_people_n32.json"
SEED = 20260821
N = 32
KEY_BASE = b"oir-metaqa-2x2-people-v1"
ARMS = [
    "ENG_UNIQUE",
    "ENG_AMBIG",
    "OPAQUE_UNIQUE",
    "OPAQUE_AMBIG",
    "OPAQUE_AMBIG_PLAN",
]


def item_key(i: int) -> bytes:
    return hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:16]


RELS = (
    "starred_actors",
    "directed_by",
    "written_by",
    "release_year",
    "in_language",
    "has_tags",
    "has_plot",
    "has_genre",
)


def parse_kb(path: Path) -> dict[str, dict[str, list[str]]]:
    """Parse WikiMovies lines: '<movie> <rel> <object>' (movie titles may contain spaces)."""
    movies: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^\d+\s+", "", line)
            hit = None
            for rel in RELS:
                marker = f" {rel} "
                if marker in line:
                    hit = rel
                    movie, rest = line.split(marker, 1)
                    break
            if hit is None:
                continue
            objs = [x.strip() for x in rest.split(",") if x.strip()]
            for o in objs:
                if o and o not in movies[movie][hit]:
                    movies[movie][hit].append(o)
    return movies


def candidates(movies: dict) -> list[dict]:
    """Same-type tails (person vs person): director vs writer from one actor."""
    out = []
    for movie, rels in movies.items():
        dirs = rels.get("directed_by", [])
        writers = rels.get("written_by", [])
        actors = rels.get("starred_actors", [])
        if len(dirs) != 1 or len(writers) != 1 or not actors:
            continue
        director, writer, actor = dirs[0], writers[0], actors[0]
        if len({director, writer, actor}) < 3:
            continue
        if "," in director or "," in writer or "," in actor:
            continue
        out.append(
            {
                "actor": actor,
                "movie": movie,
                "director": director,
                "writer": writer,
            }
        )
    return out


def unique_edges(row: dict, decoy: dict) -> list[tuple[str, str, str]]:
    return [
        (row["actor"], "starred_in", row["movie"]),
        (row["movie"], "directed_by", row["director"]),
        (decoy["actor"], "starred_in", decoy["movie"]),
        (decoy["movie"], "directed_by", decoy["director"]),
    ]


def ambig_edges(row: dict, decoy: dict) -> list[tuple[str, str, str]]:
    return [
        (row["actor"], "starred_in", row["movie"]),
        (row["movie"], "directed_by", row["director"]),
        (row["movie"], "written_by", row["writer"]),
    ]


def render(edges: list[tuple[str, str, str]], sealer: EntitySeal | None) -> str:
    uniq = list(dict.fromkeys(edges))
    if sealer is None:
        return SealRouter(uniq).render()
    return SealRouter([(h, sealer.atom(r), t) for h, r, t in uniq]).render()


def pack(cid: str, q: str, ctx: str, extra: str) -> str:
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No other files.",
            f"Format: ANSWER_PLAIN[{cid}]: <answer_or_UNKNOWN>",
            extra,
            f"##### ID {cid} #####",
            "QUESTION:",
            q,
            "",
            "CONTEXT:",
            ctx,
            "",
        ]
    )


def build() -> dict:
    sys.path.insert(0, str(ROOT / "harness"))
    from factorial_2x2_iso import two_hops as hops

    if not KB.exists():
        raise SystemExit(f"Download WikiMovies KB to {KB}")
    movies = parse_kb(KB)
    pool = candidates(movies)
    rng = random.Random(SEED)
    if len(pool) < N + 1:
        raise SystemExit(f"not enough unique director+genre+language rows: {len(pool)}")
    picked = rng.sample(pool, N)
    FREEZE.parent.mkdir(parents=True, exist_ok=True)
    FREEZE.write_text(json.dumps({"seed": SEED, "n": N, "items": picked}, indent=2))
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)
    arms = {a: {"ids": [], "item_paths": []} for a in ARMS}
    cases = []
    for i, row in enumerate(picked):
        decoy = picked[(i + 1) % N]
        u_edges = unique_edges(row, decoy)
        a_edges = list(dict.fromkeys(ambig_edges(row, decoy)))
        assert len(hops(u_edges, row["actor"])) == 1
        assert len(hops(a_edges, row["actor"])) == 2
        sealer = EntitySeal(item_key(i))
        q = f"Who directed a movie that {row['actor']} starred in?"
        assert row["actor"] in q
        plan = path_program(
            row["actor"],
            (sealer.atom("starred_in"), sealer.atom("directed_by")),
            row["director"],
        )
        specs = {
            "ENG_UNIQUE": (q, render(u_edges, None), "ARM ENG_UNIQUE: WikiMovies; English relations; one 2-hop."),
            "ENG_AMBIG": (q, render(a_edges, None), "ARM ENG_AMBIG: WikiMovies; English relations; two 2-hops (director vs writer)."),
            "OPAQUE_UNIQUE": (q, render(u_edges, sealer), "ARM OPAQUE_UNIQUE: WikiMovies; opaque relations; one 2-hop."),
            "OPAQUE_AMBIG": (q, render(a_edges, sealer), "ARM OPAQUE_AMBIG: WikiMovies; opaque relations; two 2-hops (same-type person tails)."),
            "OPAQUE_AMBIG_PLAN": (
                q + "\n\n" + plan.body,
                render(a_edges, sealer),
                "ARM OPAQUE_AMBIG_PLAN: same graph plus explicit relation sequence.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"MQA2_{arm}_{i}"
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
        "source": "WikiMovies kb (MetaQA movie graph); same-type person tails",
        "source_url": "https://github.com/rohit129/Movie_KnowledgeGraph_QA/blob/master/wiki_entities_kb.txt",
        "freeze": str(FREEZE.relative_to(ROOT)),
        "start_in_question": True,
        "keys": "per-item HMAC on relation atoms only",
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "metaqa_2x2_people_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print("wrote", out, "n", N, "pool", len(pool))
    return harness


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "harness"))
    build()
