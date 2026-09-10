#!/usr/bin/env python3
"""Official-style MetaQA 2-hop questions on the public WikiMovies KB.

Uses published 2-hop templates (Zhang et al. 2018) instantiated on facts in
wiki_entities_kb.txt. Not the 14k test-split leaderboard: a freeze of n=32
verified 2-hop items whose gold tail is reachable in the public graph.

Condition A keeps the English question (verbs can leak onto opaque relation
names). Condition B hashes question atoms except the bracketed start entity,
so verbs cannot cue directed_by / written_by.
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

from paths import repo_rel
from metaqa_2x2_iso import parse_kb  # type: ignore
from oir import EntitySeal, SealRouter, path_program

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "metaqa_official_iso"
KB = ROOT / "data" / "metaqa" / "wiki_entities_kb.txt"
FREEZE = ROOT / "data" / "metaqa" / "oir_official_2hop_n32.json"
SEED = 20260821
N = 32
KEY_BASE = b"oir-metaqa-official-iso-v1"
ARMS = [
    "PLAIN",
    "OPAQUE_REL_QENG",
    "OPAQUE_REL_QHASH",
    "OPAQUE_REL_QHASH_PLAN",
]


def item_key(i: int) -> bytes:
    return hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:16]


def index_movies(movies: dict) -> dict[str, list[tuple[str, str, str]]]:
    """person/object -> list of (head_movie_or_person, rel, tail) 2-hop facts we use."""
    by_person: dict[str, list[dict]] = defaultdict(list)
    for movie, rels in movies.items():
        dirs = rels.get("directed_by", [])
        writers = rels.get("written_by", [])
        actors = rels.get("starred_actors", [])
        genres = rels.get("has_genre", [])
        if len(dirs) == 1 and actors:
            actor = actors[0]
            if "," in actor or "," in dirs[0]:
                continue
            if genres:
                by_person[dirs[0]].append(
                    {
                        "kind": "genre_of_director",
                        "start": dirs[0],
                        "q": f"what is the genre of the films directed by [{dirs[0]}]",
                        "gold": genres[0],
                        "edges": [
                            (dirs[0], "directed", movie),
                            (movie, "has_genre", genres[0]),
                        ],
                        "gold_rels": ("directed", "has_genre"),
                        "decoy": None,
                    }
                )
            if writers and writers[0] != dirs[0] and "," not in writers[0]:
                by_person[writers[0]].append(
                    {
                        "kind": "director_of_writer",
                        "start": writers[0],
                        "q": f"who directed the movies written by [{writers[0]}]",
                        "gold": dirs[0],
                        "edges": [
                            (writers[0], "wrote", movie),
                            (movie, "directed_by", dirs[0]),
                        ],
                        "gold_rels": ("wrote", "directed_by"),
                        "decoy": None,
                    }
                )
        if len(dirs) == 1 and actors and writers and writers[0] != dirs[0]:
            actor = actors[0]
            if "," in actor:
                continue
            by_person[actor].append(
                {
                    "kind": "director_of_actor",
                    "start": actor,
                    "q": f"who directed the movies starred by [{actor}]",
                    "gold": dirs[0],
                    "edges": [
                        (actor, "starred_in", movie),
                        (movie, "directed_by", dirs[0]),
                        (movie, "written_by", writers[0]),
                    ],
                    "gold_rels": ("starred_in", "directed_by"),
                    "decoy": writers[0],
                }
            )
    return by_person


def sample_items(movies: dict) -> list[dict]:
    rng = random.Random(SEED)
    by_person = index_movies(movies)
    pool = []
    for recs in by_person.values():
        # prefer actor→director items (two same-type tails) when present
        actor_rows = [r for r in recs if r["kind"] == "director_of_actor"]
        pool.extend(actor_rows or recs[:1])
    # one item per start entity
    seen = set()
    uniq = []
    rng.shuffle(pool)
    for row in pool:
        if row["start"] in seen or row["gold"] == row["start"]:
            continue
        seen.add(row["start"])
        uniq.append(row)
        if len(uniq) >= 400:
            break
    actorish = [r for r in uniq if r["kind"] == "director_of_actor"]
    use = actorish if len(actorish) >= N else uniq
    if len(use) < N:
        raise SystemExit(f"not enough official-style 2-hop items: {len(use)}")
    return rng.sample(use, N)


STOP = frozenset({"what", "is", "the", "of", "who", "by", "a", "an"})


def hash_q_keep_entity(q: str, entity: str, sealer: EntitySeal) -> str:
    """HMAC content atoms except the bracketed start entity (Condition B)."""
    marker = f"[{entity}]"
    if marker not in q:
        raise ValueError(f"start entity not bracketed: {q!r}")

    def hash_side(s: str) -> str:
        return re.sub(
            r"[A-Za-z0-9_]+",
            lambda m: m.group(0)
            if m.group(0).lower() in STOP
            else sealer.atom(m.group(0)),
            s,
        )

    left, right = q.split(marker, 1)
    return hash_side(left) + marker + hash_side(right)


def render(edges, sealer: EntitySeal | None) -> str:
    if sealer is None:
        return SealRouter(edges).render()
    return SealRouter([(h, sealer.atom(r), t) for h, r, t in edges]).render()


def pack(cid: str, q: str, ctx: str, extra: str, *, sealed: bool) -> str:
    fmt = (
        f"Format: ANSWER_SEALED[{cid}]: <token_or_UNKNOWN>"
        if sealed
        else f"Format: ANSWER_PLAIN[{cid}]: <answer_or_UNKNOWN>"
    )
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No other files.",
            fmt,
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
    if not KB.exists():
        raise SystemExit(f"Download WikiMovies KB to {KB}")
    movies = parse_kb(KB)
    picked = sample_items(movies)
    FREEZE.parent.mkdir(parents=True, exist_ok=True)
    FREEZE.write_text(json.dumps({"seed": SEED, "n": N, "items": picked}, indent=2))
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    arms = {
        a: {
            "ids": [],
            "item_paths": [],
            "sealed_answer": False,
        }
        for a in ARMS
    }
    cases = []
    for i, row in enumerate(picked):
        sealer = EntitySeal(item_key(i))
        eng = render(row["edges"], None)
        opq = render(row["edges"], sealer)
        q_eng = row["q"]
        q_hash = hash_q_keep_entity(q_eng, row["start"], sealer)
        assert f"[{row['start']}]" in q_eng
        assert row["start"] in q_hash
        gold_path = [sealer.atom(r) for r in row["gold_rels"]]
        router = SealRouter([(h, sealer.atom(r), t) for h, r, t in row["edges"]])
        assert router.path(row["start"], gold_path) == [row["gold"]]
        plan = path_program(row["start"], tuple(gold_path), row["gold"])

        specs = {
            "PLAIN": (
                q_eng,
                eng,
                "ARM PLAIN: English MetaQA-style question; English subgraph.",
                False,
            ),
            "OPAQUE_REL_QENG": (
                q_eng,
                opq,
                "ARM OPAQUE_REL_QENG: Condition A — English question (verbs may leak); opaque relations.",
                False,
            ),
            "OPAQUE_REL_QHASH": (
                q_hash,
                opq,
                "ARM OPAQUE_REL_QHASH: Condition B — question atoms hashed except start entity; opaque relations.",
                False,
            ),
            "OPAQUE_REL_QHASH_PLAN": (
                q_hash + "\n\n" + plan.body,
                opq,
                "ARM OPAQUE_REL_QHASH_PLAN: Condition B plus explicit sealed relation sequence.",
                False,
            ),
        }
        ids = {}
        for arm, (qq, ctx, header, sealed) in specs.items():
            cid = f"MQO_{arm}_{i}"
            ids[arm] = cid
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, qq, ctx, header, sealed=sealed))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

        cases.append(
            {
                "i": i,
                "kind": row["kind"],
                "start": row["start"],
                "ids": ids,
                "gold": row["gold"],
                "decoy_hq": row.get("decoy") or "",
                "q": row["q"],
            }
        )

    harness = {
        "n": N,
        "seed": SEED,
        "protocol": "isolation",
        "source": "WikiMovies kb + published MetaQA 2-hop templates (not 14k test leaderboard)",
        "source_public": str(KB.relative_to(ROOT)),
        "keys": "per-item HMAC on relation atoms; entities English; start in q",
        "start_in_question": True,
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "metaqa_official_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print("wrote", out, "n", N, "kinds", {c["kind"] for c in cases})
    return harness


if __name__ == "__main__":
    build()
