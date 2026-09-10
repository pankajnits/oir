#!/usr/bin/env python3
"""
Synonym / paraphrase enrichment → then seal → multi-hop?

Direction of thinking (user):
  If we enrich the cleartext question with synonyms (via a model), then seal Q+C,
  does sealed multi-hop start working?

Conditions (same graphs, same seal key):
  RAW    — seal original NL
  SYN    — model paraphrase / synonym expansion (cleartext), then seal
  CANON  — force paraphrase to use graph relation atoms (weak compiler-like), then seal
  PROG   — sealed PATH_QUERY control (should saturate)

Prediction:
  SYN likely still 1-hop-stops — extra English synonyms become *new* seals that do not
  match works_at / headquartered_in edges unless those strings appear in CONTEXT.
  CANON may help if it injects the exact relation atoms that exist in the sealed graph.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter, pack_mut_batch, path_program, raw_nl_program
from oir.adapters import ceo_hq_edges, load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "synonym_enrich"
KEY = b"oir-synonym-enrich-v1"
SEED = 20260728
N = 12

# Cleartext synonym expansions written offline (simulating an enricher model).
# Kept explicit + reproducible; a live enricher agent can overwrite SYN lines.
SYN_TEMPLATES = [
    # free synonyms — do NOT use exact graph relation tokens
    "In which city is the employer of {person_disp} based?",
    "What is the head-office location of the firm where {person_disp} works?",
    "Find the HQ city for {person_disp}'s organization.",
    "Where does the company that employs {person_disp} have its headquarters?",
]

CANON_TEMPLATES = [
    # deliberately uses graph relation atoms as words (canonicalization enrichment)
    "Where is the company headquartered_in that {person} works_at?",
    "Find headquartered_in of the firm {person} works_at.",
]


def person_disp(p: str) -> str:
    return p.replace("_", " ")


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    sealer = EntitySeal(KEY)

    batches = {"RAW": [], "SYN": [], "CANON": [], "PROG": []}
    cases = []

    for i, row in enumerate(recs):
        person, hq = row["person"], row["hq"]
        triples_plain = ceo_hq_edges(row)
        sealed_triples = [sealer.triple(*e) for e in triples_plain]
        ctx = SealRouter(sealed_triples).render()
        expect = sealer.atom(hq)
        company_seal = sealer.atom(row["company"])

        raw_q = f"Where is the headquarters of the company that {person_disp(person)} works for?"
        syn_q = SYN_TEMPLATES[i % len(SYN_TEMPLATES)].format(
            person_disp=person_disp(person), person=person
        )
        canon_q = CANON_TEMPLATES[i % len(CANON_TEMPLATES)].format(
            person_disp=person_disp(person), person=person
        )

        for form, q in [("RAW", raw_q), ("SYN", syn_q), ("CANON", canon_q)]:
            cid = f"SYNENR_{form}_{i}"
            # seal the NL question text (enrichment already applied in cleartext)
            sealed_q = sealer.text(q)
            body = f"QUESTION:\n{sealed_q}"
            batches[form].append((cid, raw_nl_program(body), ctx))
            cases.append(
                {
                    "id": cid,
                    "form": form,
                    "i": i,
                    "person": person,
                    "company": row["company"],
                    "hq": hq,
                    "expect": expect,
                    "company_seal": company_seal,
                    "q_clear": q,
                    "q_sealed": sealed_q,
                    "relation_atoms_in_q": {
                        "works_at": "works_at" in q,
                        "headquartered_in": "headquartered_in" in q,
                    },
                }
            )

        # PROG control
        cid = f"SYNENR_PROG_{i}"
        prog = path_program(person, ("works_at", "headquartered_in"), hq).seal(sealer)
        prog.meta["start"] = sealer.atom(person)
        prog.meta["rels"] = [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        batches["PROG"].append((cid, prog, ctx))
        cases.append(
            {
                "id": cid,
                "form": "PROG",
                "i": i,
                "person": person,
                "company": row["company"],
                "hq": hq,
                "expect": expect,
                "company_seal": company_seal,
                "q_clear": prog.body,
            }
        )

    RUNS.mkdir(parents=True, exist_ok=True)
    paths = {}
    headers = {
        "RAW": "Sealed original NL (no synonym enrichment).",
        "SYN": "Cleartext synonym/paraphrase enrichment, THEN sealed (free synonyms).",
        "CANON": "Cleartext canonicalization to graph relation words, THEN sealed.",
        "PROG": "Sealed PATH_QUERY control.",
    }
    for form, items in batches.items():
        d = RUNS / f"{form}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        # pack_mut_batch expects Program; for NL we already put sealed text in body
        text = pack_mut_batch(items, headers[form], seal_question=False)
        p = d / "BATCH.txt"
        p.write_text(text)
        paths[form] = str(p)

    # Also emit enricher prompt pack for optional live model rewrite
    enricher = []
    for c in cases:
        if c["form"] == "RAW":
            enricher.append(
                {
                    "id": c["id"].replace("RAW", "SYN_LIVE"),
                    "instruction": (
                        "Paraphrase the question using synonyms. Keep the same meaning. "
                        "Do NOT use the exact tokens works_at or headquartered_in. "
                        "Return only the paraphrased question."
                    ),
                    "question": c["q_clear"],
                }
            )
    (RESULTS / "synonym_enrich_enricher_jobs.json").write_text(json.dumps(enricher, indent=2))

    harness = {
        "n": N,
        "key_note": "oir-synonym-enrich-v1",
        "claim": (
            "Test whether synonym enrichment before sealing restores multi-hop; "
            "CANON injects graph relation atoms; SYN uses free synonyms."
        ),
        "paths": paths,
        "cases": cases,
        "rev": sealer.rev,
    }
    (RESULTS / "synonym_enrich_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": N, "paths": paths, "n_cases": len(cases)}, indent=2))


if __name__ == "__main__":
    build()
