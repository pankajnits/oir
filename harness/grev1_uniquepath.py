#!/usr/bin/env python3
"""G-Rev1 unique-path isolation (the well-posed gate).

CLAIM: ambiguous sealed edges → UNKNOWN is *ambiguity*, not missing ID reasoning.
Complex CX3_SEAL_NL 8/8 was unique 3-hop + start in Q, but *batched* on one HMAC key.

This suite: same HR/TICKET/ONCALL unique 3-hop, sealed entities+relations,
sealed NL, NO PATH, one quiz per file, *per-item HMAC key* (novel IDs).

If iso saturates: unique-path composition under opacity is closed.
If it collapses: batched 8/8 was a shared-seal protocol confound.

Not SQL. Not city-vs-country underspecification.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter
from use_case_complex import world_hr, world_ticket, world_oncall, render_complex
from wilson_cis import wilson
from grev1_fullq_prog import seal_question

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "grev1_uniquepath"
SEED = 20260817
N = 6


def pack(cid: str, q: str, ctx: str) -> str:
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. Do not open other files.",
            f"Format: ANSWER_SEALED[{cid}]: <seal_or_UNKNOWN>",
            "If more than one reading is possible, output UNKNOWN.",
            "",
            "ARM UNIQUE_PATH: unique 3-hop from START. Entities and relations sealed. No PATH. No legend. One quiz.",
            "",
            f"##### ID {cid} #####",
            "QUESTION:",
            q,
            "",
            "CONTEXT:",
            ctx,
            "",
        ]
    )


def build():
    graph = json.loads((ROOT / "data/real/wikidata_ceo_hops_v2.json").read_text())
    rng = random.Random(SEED)
    recs = graph[:]
    rng.shuffle(recs)
    makers = [world_hr, world_ticket, world_oncall]

    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    cases = []
    for i in range(N):
        w = makers[i % 3](rng, recs, i * 5)
        sealer = EntitySeal(rng.randbytes(16))
        sealed_edges = [sealer.triple(*e) for e in w["edges"]]
        gold = sealer.atom(w["end"])
        start = sealer.atom(w["start"])
        rels = [sealer.atom(r) for r in w["rels"]]
        outs = SealRouter(sealed_edges).path(start, rels)
        assert list(dict.fromkeys(outs)) == [gold], (w["use"], outs)

        trap = sealer.atom(recs[i * 5 + 1]["hq"]) if recs[i * 5 + 1]["hq"] != w["end"] else sealer.atom("TRAP")
        cid = f"GREV1_UP_{i}"
        name = w["start"].replace("_", " ")
        if name in w["q3"]:
            q = seal_question(w["q3"].replace(name, start), sealer, {start})
        else:
            q = seal_question(w["q3"] + f" {start}", sealer, {start})
        ctx = render_complex(w, sealer=sealer)
        path = RUNS / f"item_{i}" / "prompt.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pack(cid, q, ctx))
        cases.append(
            {
                "i": i,
                "id": cid,
                "use": w["use"],
                "gold": gold,
                "trap": trap,
                "start": start,
                "start_in_q": start in q,
                "path": str(path),
                "iso": True,
                "per_item_key": True,
            }
        )

    h = {
        "n": N,
        "suite": "grev1_uniquepath",
        "seed": SEED,
        "nonclaim": "Unique 3-hop. Isolation. Per-item HMAC. No PATH. Validates complex SEAL_NL, not city/country NONE.",
        "cases": cases,
    }
    out = RESULTS / "grev1_uniquepath_harness.json"
    out.write_text(json.dumps(h, indent=2))
    print(json.dumps({"n": N, "start_in_q": sum(1 for c in cases if c["start_in_q"]), "out": str(out)}, indent=2))


def score(model: str):
    import re

    H = json.loads((RESULTS / "grev1_uniquepath_harness.json").read_text())
    SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
    preds = {}
    d = RESULTS / f"grev1_uniquepath_replies_{model}"
    if d.exists():
        for p in d.rglob("*.txt"):
            for m in SEAL.finditer(p.read_text()):
                preds[m.group(1)] = m.group(2).strip()
    rows = []
    for c in H["cases"]:
        pred = preds.get(c["id"], "MISSING")
        if pred == c["gold"]:
            kind = "gold"
        elif pred.upper() == "UNKNOWN":
            kind = "unknown"
        elif pred == c.get("trap"):
            kind = "trap"
        elif pred == "MISSING":
            kind = "missing"
        else:
            kind = "other"
        rows.append({**{k: v for k, v in c.items() if k != "path"}, "pred": pred, "kind": kind, "ok": kind == "gold"})
    k = sum(1 for r in rows if r["ok"])
    n = H["n"]
    summary = {
        "score": f"{k}/{n}",
        "wilson": wilson(k, n),
        "unknown": sum(1 for r in rows if r["kind"] == "unknown"),
        "trap": sum(1 for r in rows if r["kind"] == "trap"),
        "missing": sum(1 for r in rows if r["kind"] == "missing"),
    }
    path = RESULTS / f"grev1_uniquepath_{model}.json"
    path.write_text(json.dumps({"model": model, "n": n, "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else "gpt56")
    else:
        build()
