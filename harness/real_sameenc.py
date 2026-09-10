#!/usr/bin/env python3
"""
Real-data same-encoding OIR suite (goal-aligned).

Source: Wikidata CEO→company→HQ (online pull in data/real/).

All conditions: ONE seal map for question + context. No English handle legends.

A. CANON  — question uses canonical atoms (works_at, headquartered_in) sealed
B. PARA   — paraphrased English sealed (should be harder / fail) — diagnosis
C. STRUCT — structural pure-sink rule, no relation words in Q
D. DEMO   — 2 sealed demos then query on held-out real people (induction)

Distractors: owned_by / partner_of with non-sink tails so STRUCT is identifiable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data/real/wikidata_ceo_hops.json").read_text())
RESULTS = ROOT / "results"
KEY = b"oir-real-sameenc-v1"
SEED = 20260724


class EntitySeal:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def atom(self, a: str) -> str:
        if a not in self.fwd:
            d = hmac.new(self.key, a.encode(), hashlib.sha256).digest()
            t = "E" + d[:6].hex()
            self.fwd[a] = t
            self.rev[t] = a
        return self.fwd[a]

    def seal_words(self, text: str) -> str:
        import re
        return "".join(
            self.atom(p) if re.fullmatch(r"[A-Za-z0-9_]+", p) else p
            for p in re.findall(r"[A-Za-z0-9_]+|[^A-Za-z0-9_]+", text)
        )


def render(sealer, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def build_graph(row, all_rows, rng):
    """person works_at company; company headquartered_in hq; distractors."""
    person, company, hq = row["person"], row["company"], row["hq"]
    # pick another company as decoy
    others = [r for r in all_rows if r["company"] != company]
    decoy = rng.choice(others) if others else row
    dco, dhq = decoy["company"], decoy["hq"]
    hold, part = f"Hold_{company}", f"Part_{company}"
    edges = [
        (person, "works_at", company),
        (company, "headquartered_in", hq),
        (dco, "headquartered_in", dhq),
        (company, "owned_by", hold),
        (hold, "meta_of", f"Meta_{company}"),
        (company, "partner_of", part),
        (part, "meta_of", f"PMeta_{company}"),
        (f"DecoyPerson_{company}", "works_at", dco),
    ]
    return edges, person, hq


def write_batch(name: str, header: str, items: list[tuple[str, str]]):
    d = ROOT / "runs" / f"real_{name}_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "Same encoding on question and context. Opaque IDs. Same ID = same thing.\n",
        "No external knowledge. Answer from CONTEXT only.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        header + "\n",
    ]
    for cid, body in items:
        lines.append(f"\n##### ID {cid} #####\n{body}\n")
    path = d / f"BATCH_{name}.txt"
    path.write_text("\n".join(lines))
    return str(path)


def main():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    # use up to 16 real hops; first 4 demos, rest quiz for DEMO cond; CANON/PARA/STRUCT on quiz set
    rows = [r for r in DATA if r["person"] and r["company"] and r["hq"]]
    # dedupe persons
    seen = set()
    uniq = []
    for r in rows:
        if r["person"] in seen:
            continue
        seen.add(r["person"])
        uniq.append(r)
    rows = uniq[:16]
    assert len(rows) >= 8, len(rows)

    demo_rows = rows[:3]
    quiz_rows = rows[3:11]  # 8 quiz items

    cases = []
    canon_items, para_items, struct_items, demo_items = [], [], [], []

    # Prewarm relations
    for r in ("works_at", "headquartered_in", "owned_by", "partner_of", "meta_of"):
        sealer.atom(r)

    for i, row in enumerate(quiz_rows):
        edges, person, hq = build_graph(row, rows, rng)
        ctx = render(sealer, edges)
        exp = sealer.atom(hq)

        # A. CANON — same encoding, canonical relation words in Q
        q_canon = f"Where is the company headquartered_in that {person} works_at ? Reply location seal only."
        cid = f"REAL_CANON_{i}"
        canon_items.append(
            (
                cid,
                f"QUESTION:\n{sealer.seal_words(q_canon)}\n\nCONTEXT:\n{ctx}",
            )
        )
        cases.append({"id": cid, "cond": "canon", "expect": exp, "plain_hq": hq, "person": person})

        # B. PARA — paraphrase (different atoms) same seal key
        q_para = f"In which city is the employer of {person} based ? Reply location seal only."
        cidp = f"REAL_PARA_{i}"
        para_items.append(
            (
                cidp,
                f"QUESTION:\n{sealer.seal_words(q_para)}\n\nCONTEXT:\n{ctx}",
            )
        )
        cases.append({"id": cidp, "cond": "para", "expect": exp, "plain_hq": hq, "person": person})

        # C. STRUCT — no relation lexicon; pure-sink 2-hop
        cids = f"REAL_STRUCT_{i}"
        struct_items.append(
            (
                cids,
                f"SUBJECT {sealer.atom(person)}\n"
                f"From SUBJECT follow exactly two edges to a node that never appears "
                f"as a LEFT/head column entry. Return that end seal or UNKNOWN.\n\nCONTEXT:\n{ctx}",
            )
        )
        cases.append({"id": cids, "cond": "struct", "expect": exp, "plain_hq": hq, "person": person})

    # D. DEMO — sealed demos with canonical Q, then quiz
    demo_blobs = []
    for j, row in enumerate(demo_rows):
        edges, person, hq = build_graph(row, rows, rng)
        q = f"Where is the company headquartered_in that {person} works_at ? Reply location seal only."
        demo_blobs.append(
            f"DEMO {j}:\nQUESTION:\n{sealer.seal_words(q)}\n\nCONTEXT:\n{render(sealer, edges)}\n\n"
            f"ANSWER_SEALED: {sealer.atom(hq)}\n"
        )
    for i, row in enumerate(quiz_rows):
        edges, person, hq = build_graph(row, rows, rng)
        q = f"Where is the company headquartered_in that {person} works_at ? Reply location seal only."
        cid = f"REAL_DEMO_{i}"
        demo_items.append(
            (
                cid,
                f"QUESTION:\n{sealer.seal_words(q)}\n\nCONTEXT:\n{render(sealer, edges)}",
            )
        )
        cases.append({"id": cid, "cond": "demo", "expect": sealer.atom(hq), "plain_hq": hq, "person": person})

    write_batch("canon", "Canonical sealed question (relation atoms match CONTEXT).", canon_items)
    write_batch("para", "Paraphrased sealed question (surface words differ).", para_items)
    write_batch("struct", "Structural rule only (language-free intent).", struct_items)
    # demo batch includes demos in header
    d = ROOT / "runs" / "real_demo_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "Same encoding. Learn the path type from DEMOS, then answer QUIZ IDs.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n\n=== DEMOS ===\n",
        "\n".join(demo_blobs),
        "\n=== QUIZ ===\n",
    ]
    for cid, body in demo_items:
        lines.append(f"\n##### ID {cid} #####\n{body}\n")
    (d / "BATCH_demo.txt").write_text("\n".join(lines))

    harness = {
        "goal": "same-encoding Q+C only; real Wikidata multi-hop",
        "source": "data/real/wikidata_ceo_hops.json",
        "n_quiz_per_cond": len(quiz_rows),
        "cases": cases,
        "rev": sealer.rev,
        "companies": sorted({r["company"] for r in rows}),
    }
    (RESULTS / "real_sameenc_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"quiz": len(quiz_rows), "conds": 4, "total_cases": len(cases)}, indent=2))


if __name__ == "__main__":
    main()
