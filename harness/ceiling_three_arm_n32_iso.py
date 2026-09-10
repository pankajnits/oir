#!/usr/bin/env python3
"""Isolation three-arm ceiling N=32. Does not overwrite locked n=12 or n=24 batch."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program
from paths import repo_rel
from oir.adapters import ceo_hq_edges, load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "ceiling_three_arm_n32_iso"
SEED = 20260820
N = 32
KEY_BASE = b"oir-ceil-n32-iso-v1"


def item_key(i: int) -> bytes:
    return hashlib.sha256(KEY_BASE + str(i).encode()).digest()[:16]


def pack_plain(cid: str, body: str, ctx: str) -> str:
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only.",
            "Format: ANSWER_PLAIN[<id>]: <city_or_UNKNOWN>",
            "",
            "ARM A: plaintext PATH binder (language-readable symbols).",
            "",
            f"##### ID {cid} #####\n{body}\n\nCONTEXT:\n{ctx}\n",
        ]
    )


def pack_sealed(cid: str, body: str, ctx: str, header: str) -> str:
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>",
            "",
            header,
            "",
            f"##### ID {cid} #####\n{body}\n\nCONTEXT:\n{ctx}\n",
        ]
    )


def build() -> None:
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    RUNS.mkdir(parents=True, exist_ok=True)
    for p in RUNS.rglob("prompt.txt"):
        p.unlink()

    cases = []
    arms = {
        "PLAIN_PROG": {"ids": [], "item_paths": []},
        "SEAL_PROG": {"ids": [], "item_paths": []},
        "SEAL_NL": {"ids": [], "item_paths": []},
    }

    for i, row in enumerate(recs):
        sealer = EntitySeal(item_key(i))
        person, hq, company = row["person"], row["hq"], row["company"]
        edges = ceo_hq_edges(row)
        plain_ctx = SealRouter(edges).render()
        sealed_triples = [sealer.triple(*e) for e in edges]
        sealed_ctx = SealRouter(sealed_triples).render()
        outs = SealRouter(sealed_triples).path(
            sealer.atom(person),
            [sealer.atom("works_at"), sealer.atom("headquartered_in")],
        )
        assert list(dict.fromkeys(outs)) == [sealer.atom(hq)], (outs, hq)

        prog_plain = path_program(person, ("works_at", "headquartered_in"), hq)
        prog_sealed = prog_plain.seal(sealer)
        prog_sealed.meta["start"] = sealer.atom(person)
        prog_sealed.meta["rels"] = [
            sealer.atom("works_at"),
            sealer.atom("headquartered_in"),
        ]
        q = (
            f"Where is the headquarters of the company that "
            f"{person.replace('_', ' ')} works for?"
        )

        cid_a, cid_b, cid_c = f"CEIL32_PLAIN_{i}", f"CEIL32_SEALPROG_{i}", f"CEIL32_SEALNL_{i}"
        pa = RUNS / "PLAIN_PROG" / f"item_{i}" / "prompt.txt"
        pb = RUNS / "SEAL_PROG" / f"item_{i}" / "prompt.txt"
        pc = RUNS / "SEAL_NL" / f"item_{i}" / "prompt.txt"
        pa.parent.mkdir(parents=True, exist_ok=True)
        pb.parent.mkdir(parents=True, exist_ok=True)
        pc.parent.mkdir(parents=True, exist_ok=True)
        pa.write_text(pack_plain(cid_a, prog_plain.body, plain_ctx))
        pb.write_text(
            pack_sealed(
                cid_b,
                prog_sealed.body,
                sealed_ctx,
                "ARM B: same PATH binder with opaque sealed atoms.",
            )
        )
        pc.write_text(
            pack_sealed(
                cid_c,
                f"QUESTION:\n{sealer.text(q)}",
                sealed_ctx,
                "ARM C: sealed free NL — no program.",
            )
        )
        arms["PLAIN_PROG"]["ids"].append(cid_a)
        arms["PLAIN_PROG"]["item_paths"].append(repo_rel(pa))
        arms["SEAL_PROG"]["ids"].append(cid_b)
        arms["SEAL_PROG"]["item_paths"].append(repo_rel(pb))
        arms["SEAL_NL"]["ids"].append(cid_c)
        arms["SEAL_NL"]["item_paths"].append(repo_rel(pc))
        cases.append(
            {
                "i": i,
                "person": person,
                "company": company,
                "hq": hq,
                "id_plain": cid_a,
                "id_sealprog": cid_b,
                "id_sealnl": cid_c,
                "expect_plain": hq,
                "expect_seal": sealer.atom(hq),
                "company_seal": sealer.atom(company),
            }
        )

    harness = {
        "n": N,
        "seed": SEED,
        "protocol": "isolation",
        "keys": "per-item HMAC",
        "arms": arms,
        "cases": cases,
        "sealrouter_ceiling": f"{N}/{N}",
    }
    out = RESULTS / "ceiling_three_arm_n32_iso_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": N, "protocol": "isolation", "sealrouter": f"{N}/{N}", "harness": str(out)}, indent=2))


if __name__ == "__main__":
    build()
