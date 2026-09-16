#!/usr/bin/env python3
"""Header x decoy ablation on the WIKI-H5 items (pre-publication review follow-up).

Motivation. On the same 32 people, WIKI-H5 OPAQUE_AMBIG (OpenAI 6/32) and
ambig_curve K2 (OpenAI 29/32) share question, format, "Use CONTEXT only",
English entities, HMAC relations, gold-first order and two same-type routes.
They differ in (a) the ARM header line, (b) the decoy route -- cyclic record
i+1 in WIKI-H5, but the *first eligible pool record* in K2, which is the same
route (Cogent_Communications -> Washington_DC) for all 32 items -- (c) the HMAC
key, and (d) case ids that name the arm (F22_OPAQUE_AMBIG_i, CURVE_K2_i).

This suite holds (c) at the WIKI-H5 per-item key, replaces (d) with hashed case
ids, and crosses (a) x (b):

  header  H5    ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start.
          K2    ARM K2: opaque relations; 2 same-type 2-hop(s) from start.
          NONE  no ARM line
  decoy   CYC   record i+1 (WIKI-H5 construction; varies by item)
          CRV   first eligible pool record (ambig_curve construction; constant)

plus ENG_NONE_CYC (English relations, no header, cyclic decoy): is two-path
abstention with readable relations header-driven?

OPQ_H5_CYC has the exact WIKI-H5 CONTEXT (tests check this), so it doubles as a
same-prompt replication differing only in the case id.

Pre-specified reading (write it down before running):
  * header-driven  -> OPQ_NONE_* well above OPQ_H5_*, within each decoy level;
  * decoy-driven   -> OPQ_*_CRV well above OPQ_*_CYC, within each header level;
  * id-driven      -> OPQ_H5_CYC well above locked WIKI-H5 6/32.
Report all seven cells, outcome counts (gold/decoy/UNKNOWN/NO_OUTPUT/other)
and the paired exact McNemar tests printed by ``score``.

  python3 harness/header_decoy_ablation_iso.py build
  python3 harness/run_openai_iso_harness.py results/header_decoy_ablation_iso_harness.json gpt56abl \\
      --model gpt-5.6-sol --max-completion-tokens 4096 --reasoning-effort medium
  AGENT_API_KEY=... python3 harness/run_iso_agent_harness.py \\
      results/header_decoy_ablation_iso_harness.json composer25abl composer-2.5 --preamble none
  AGENT_API_KEY=... python3 harness/run_iso_agent_harness.py \\
      results/header_decoy_ablation_iso_harness.json grok45abl grok-4.5 --preamble none
  python3 harness/header_decoy_ablation_iso.py score gpt56abl --force
  python3 harness/header_decoy_ablation_iso.py score composer25abl --force
  python3 harness/header_decoy_ablation_iso.py score grok45abl --force
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from lockjson import write_lock  # noqa: E402
from factorial_2x2_iso import (  # noqa: E402
    SEED,
    SOURCE,
    N,
    ambig_edges,
    item_key,
    pack,
    render,
    two_hops,
)
from oir import EntitySeal  # noqa: E402
from oir.adapters import load_json_records  # noqa: E402
from paths import repo_rel  # noqa: E402
from reply_parse import classify, first_pred  # noqa: E402

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "header_decoy_ablation_iso"
HARNESS = RESULTS / "header_decoy_ablation_iso_harness.json"
CID_SALT = b"oir-header-decoy-ablation-v1"
HEADERS = {
    "H5": "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start.",
    "K2": "ARM K2: opaque relations; 2 same-type 2-hop(s) from start.",
    "NONE": None,
}
ARMS = [(f"OPQ_{h}_{d}", h, d, True) for h in ("H5", "K2", "NONE") for d in ("CYC", "CRV")]
ARMS.append(("ENG_NONE_CYC", "NONE", "CYC", False))


def neutral_cid(arm: str, i: int) -> str:
    return "HDA_" + hashlib.sha256(CID_SALT + arm.encode() + b":" + str(i).encode()).hexdigest()[:10]


def curve_decoy(row: dict, pool: list[dict]) -> dict:
    """ambig_curve_iso's first decoy: first pool record not sharing company/hq/person."""
    for r in pool:
        if r["company"] == row["company"] or r["hq"] == row["hq"] or r["person"] == row["person"]:
            continue
        return r
    raise ValueError(f"no eligible curve decoy for {row['person']}")


def build(runs: Path = RUNS, harness_path: Path = HARNESS) -> dict:
    recs = load_json_records(SOURCE)
    pool = [r for r in recs if r["hq"] and r["person"] and r["company"]]
    picked = random.Random(SEED).sample(pool, N)
    if runs.exists():
        for p in runs.rglob("prompt.txt"):
            p.unlink()
    runs.mkdir(parents=True, exist_ok=True)
    arms = {
        name: {"ids": [], "item_paths": [], "header": hk, "decoy": dk,
               "relations": "opaque" if opaque else "english"}
        for name, hk, dk, opaque in ARMS
    }
    cases = []
    for i, row in enumerate(picked):
        cyc = picked[(i + 1) % N]
        if cyc["hq"] == row["hq"] or cyc["person"] == row["person"]:
            raise ValueError(f"item {i}: cyclic decoy shares hq/person with gold")
        decoys = {"CYC": cyc, "CRV": curve_decoy(row, pool)}
        sealer = EntitySeal(item_key(i))
        q = f"What city is the headquarters of the company led by {row['person']}?"
        case = {"i": i, "person": row["person"], "gold": row["hq"],
                "decoy_hq": {k: d["hq"] for k, d in decoys.items()}, "ids": {}}
        for name, hk, dk, opaque in ARMS:
            edges = ambig_edges(row, decoys[dk])
            EntitySeal.assert_raw_injective(x for e in edges for x in e)
            hops = two_hops(edges, row["person"])
            assert len(hops) == 2 and sum(h[2] == row["hq"] for h in hops) == 1, hops
            cid = neutral_cid(name, i)
            path = runs / name / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            ctx = render(edges, sealer if opaque else None)
            path.write_text(pack(cid, q, ctx, sealed_ans=False, extra=HEADERS[hk]))
            arms[name]["ids"].append(cid)
            arms[name]["item_paths"].append(repo_rel(path))
            case["ids"][name] = cid
        cases.append(case)
    harness = {
        "n": N, "seed": SEED, "protocol": "isolation", "suite": "header_decoy_ablation_iso",
        "source": str(SOURCE.relative_to(ROOT)),
        "keys": "WIKI-H5 per-item HMAC (oir-fact-2x2-iso-v1) on relation atoms; entities English",
        "case_ids": "hashed case ids (no arm names in Format/ID lines)",
        "factors": {"header": list(HEADERS), "decoy": ["CYC", "CRV"]},
        "arms": arms, "cases": cases,
    }
    harness_path.parent.mkdir(parents=True, exist_ok=True)
    harness_path.write_text(json.dumps(harness, indent=2, ensure_ascii=False) + "\n")
    print("wrote", harness_path, "arms", len(arms), "items", N)
    return harness


def _mcnemar(b: int, c: int) -> float:
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, j) for j in range(min(b, c) + 1)) / 2**n)


def score(tag: str, harness_path: Path = HARNESS, results_dir: Path = RESULTS,
          *, force: bool = False) -> dict:
    h = json.loads(harness_path.read_text())
    reply_root = results_dir / f"{harness_path.stem}_replies_{tag}"
    cells, ok = {}, {}
    for arm, meta in h["arms"].items():
        c: Counter = Counter()
        hits: list[bool | None] = []
        for i, case in enumerate(h["cases"]):
            f = reply_root / arm / f"item_{i}.txt"
            if not f.exists():
                c["missing"] += 1
                hits.append(None)
                continue
            text = f.read_text()
            kind, pred = classify(text), first_pred(text)
            incomplete = kind in ("error", "no_output", "legacy_empty")
            if kind == "error":
                c["error"] += 1
            elif kind in ("no_output", "legacy_empty"):
                c["no_output"] += 1
            elif pred == case["gold"]:
                c["gold"] += 1
            elif pred.upper() == "UNKNOWN":
                c["unknown"] += 1
            elif pred == case["decoy_hq"][meta["decoy"]]:
                c["decoy"] += 1
            else:
                c["other"] += 1
            # Complete-case McNemar: missing and incomplete (empty/error) are
            # excluded from the pair. They still appear in cell counts. ITT
            # (incomplete = not-gold) is not the reported p-value.
            hits.append(None if incomplete else pred == case["gold"])
        cells[arm] = dict(c)
        ok[arm] = hits
    pairs = [(f"OPQ_{a}_{d}", f"OPQ_{b}_{d}") for d in ("CYC", "CRV")
             for a, b in (("H5", "NONE"), ("K2", "NONE"), ("H5", "K2"))]
    pairs += [(f"OPQ_{hk}_CYC", f"OPQ_{hk}_CRV") for hk in ("H5", "K2", "NONE")]
    contrasts = []
    for a, b in pairs:
        both = [i for i in range(len(h["cases"])) if ok[a][i] is not None and ok[b][i] is not None]
        only_a = sum(1 for i in both if ok[a][i] and not ok[b][i])
        only_b = sum(1 for i in both if ok[b][i] and not ok[a][i])
        contrasts.append({"a": a, "b": b, "n_paired": len(both), "a_only": only_a,
                          "b_only": only_b, "mcnemar_exact_p": _mcnemar(only_a, only_b)})
    out = {"tag": tag, "harness": repo_rel(harness_path), "cells": cells, "contrasts": contrasts}
    dest = results_dir / f"{harness_path.stem.replace('_harness', '')}_{tag}.json"
    write_lock(dest, out, force=force)
    for arm, c in cells.items():
        print(f"{arm:14s} {c}")
    for x in contrasts:
        print(f"{x['a']} vs {x['b']}: {x['a_only']} vs {x['b_only']} (p={x['mcnemar_exact_p']:.2e})")
    print("wrote", dest)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build()
    elif cmd == "score":
        force = "--force" in sys.argv
        argv = [a for a in sys.argv[2:] if a != "--force"]
        if not argv:
            raise SystemExit("usage: header_decoy_ablation_iso.py score TAG [harness.json] [--force]")
        harness = Path(argv[1]) if len(argv) > 1 else HARNESS
        score(argv[0], harness_path=harness, force=force)
    else:
        raise SystemExit("usage: header_decoy_ablation_iso.py build | score TAG [--force]")
