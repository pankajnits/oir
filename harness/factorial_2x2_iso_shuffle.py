#!/usr/bin/env python3
"""Gold/decoy listing shuffle on the locked Wikidata two-path graphs.

Same 32 CEOs, HMAC keys, questions, and edges as factorial_2x2_iso.py.
Only the CONTEXT listing order of the two 2-hops changes (16 gold-first,
16 decoy-first). Does not rewrite runs/factorial_2x2_iso/.

  python3 harness/factorial_2x2_iso_shuffle.py
  python3 harness/run_openai_iso_harness.py results/factorial_2x2_iso_shuffle_harness.json gpt56
  python3 harness/score_factorial_2x2.py gpt56 factorial_2x2_iso_shuffle_harness
  python3 harness/factorial_2x2_iso_shuffle.py report
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from lockjson import write_lock
from paths import repo_rel
from factorial_2x2_iso import (  # type: ignore
    N,
    SEED,
    SOURCE,
    item_key,
    pack,
    render,
    two_hops,
)
from oir import EntitySeal, SealRouter
from oir.adapters import load_json_records

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "factorial_2x2_iso_shuffle"
SHUFFLE_SEED = 20260907
ARMS = ["ENG_AMBIG", "OPAQUE_AMBIG"]


def picked_rows() -> list[dict]:
    recs = load_json_records(SOURCE)
    rng = random.Random(SEED)
    pool = [r for r in recs if r["hq"] and r["person"] and r["company"]]
    return rng.sample(pool, N)


def decoy_for(picked: list[dict], i: int) -> dict:
    row = picked[i]
    decoy = picked[(i + 1) % N]
    if decoy["hq"] == row["hq"] or decoy["person"] == row["person"]:
        return {
            "person": f"DecoyPerson_{i}",
            "company": f"DecoyCo_{i}",
            "hq": f"DecoyCity_{i}",
        }
    return decoy


def ordered_ambig_edges(row: dict, decoy: dict, gold_first: bool) -> list[tuple[str, str, str]]:
    p, c, hq = row["person"], row["company"], row["hq"]
    gold = [(p, "works_at", c), (c, "headquartered_in", hq)]
    alt = [
        (p, "partner_of", decoy["company"]),
        (decoy["company"], "located_in", decoy["hq"]),
    ]
    return gold + alt if gold_first else alt + gold


def gold_first_set() -> set[int]:
    return set(random.Random(SHUFFLE_SEED).sample(range(N), N // 2))


def build() -> dict:
    picked = picked_rows()
    gold_first_idx = gold_first_set()
    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    arms = {a: {"ids": [], "item_paths": []} for a in ARMS}
    cases = []
    for i, row in enumerate(picked):
        decoy = decoy_for(picked, i)
        gold_first = i in gold_first_idx
        a_edges = ordered_ambig_edges(row, decoy, gold_first)
        hops = two_hops(a_edges, row["person"])
        assert len(hops) == 2, hops
        assert {h[2] for h in hops} == {row["hq"], decoy["hq"]}
        first_tail = hops[0][2]
        if gold_first:
            assert first_tail == row["hq"]
        else:
            assert first_tail == decoy["hq"]

        sealer = EntitySeal(item_key(i))
        q = (
            "What city is the headquarters of the company led by "
            f"{row['person']}?"
        )
        a_eng = render(a_edges, None)
        a_op = render(a_edges, sealer)
        gold_path = [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        router = SealRouter([(h, sealer.atom(r), t) for h, r, t in a_edges])
        assert router.path(row["person"], gold_path) == [row["hq"]]
        specs = {
            "ENG_AMBIG": (
                q,
                a_eng,
                "ARM ENG_AMBIG: English relations; two 2-hops from start.",
            ),
            "OPAQUE_AMBIG": (
                q,
                a_op,
                "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"F22S_{arm}_{i}"
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
                "company": row["company"],
                "hq": row["hq"],
                "decoy_hq": decoy["hq"],
                "gold_first": gold_first,
                "first_listed_hq": row["hq"] if gold_first else decoy["hq"],
                "ambig_hops": 2,
                "ids": ids,
                "gold": row["hq"],
            }
        )

    n_gold = sum(1 for c in cases if c["gold_first"])
    assert n_gold == N // 2, n_gold
    harness = {
        "n": N,
        "seed": SEED,
        "shuffle_seed": SHUFFLE_SEED,
        "protocol": "isolation",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_public": "Same Wikidata CEO slice and HMAC keys as factorial_2x2_iso; CONTEXT order shuffled",
        "keys": "per-item HMAC on relation atoms only; entities remain English",
        "start_in_question": True,
        "intervention": "gold/decoy 2-hop listing order (16 gold-first, 16 decoy-first)",
        "primary_lock_untouched": "runs/factorial_2x2_iso/",
        "n_gold_first": n_gold,
        "n_decoy_first": N - n_gold,
        "factors": ["listing_order"],
        "arms": arms,
        "cases": cases,
    }
    out = RESULTS / "factorial_2x2_iso_shuffle_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print("wrote", out, "n", N, "gold_first", n_gold, "decoy_first", N - n_gold)
    return harness


def report(tag: str = "gpt56", *, force: bool = False) -> dict:
    H = json.loads((RESULTS / "factorial_2x2_iso_shuffle_harness.json").read_text())
    scored = json.loads((RESULTS / f"factorial_2x2_iso_shuffle_{tag}.json").read_text())
    by_id = {row["id"]: row for row in scored["rows"]}
    out: dict = {"model": tag, "by_arm": {}}
    for arm in ARMS:
        buckets = {
            "gold_first": {"ok": 0, "n": 0, "unknown": 0, "decoy": 0},
            "decoy_first": {"ok": 0, "n": 0, "unknown": 0, "decoy": 0},
        }
        for c in H["cases"]:
            row = by_id[c["ids"][arm]]
            key = "gold_first" if c["gold_first"] else "decoy_first"
            b = buckets[key]
            b["n"] += 1
            pred = row["pred"]
            if row["ok"]:
                b["ok"] += 1
            elif pred.upper() == "UNKNOWN":
                b["unknown"] += 1
            elif pred == c["decoy_hq"]:
                b["decoy"] += 1
        out["by_arm"][arm] = {
            "overall": scored["summary"][arm],
            **{
                k: {
                    "score": f"{v['ok']}/{v['n']}",
                    "unknown": v["unknown"],
                    "decoy": v["decoy"],
                }
                for k, v in buckets.items()
            },
        }
    path = RESULTS / f"factorial_2x2_iso_shuffle_{tag}_order.json"
    write_lock(path, out, force=force)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("wrote", path)
    return out


if __name__ == "__main__":
    force = "--force" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--force"]
    if argv[:1] == ["report"]:
        if len(argv) < 2:
            raise SystemExit("usage: factorial_2x2_iso_shuffle.py report TAG [--force]")
        report(argv[1], force=force)
    else:
        build()
