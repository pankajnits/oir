#!/usr/bin/env python3
"""
Long-context OIR: ~100k-token sealed CONTEXT from real data + pad.

Modern LLMs advertise 1M context — does sealed multi-hop / follow-up / complex
QA work when C is ~100k tokens of opaque seals?

Design
------
- Needle: real Wikidata CEO→company→HQ (73)
- Filler: OpenData500 company→city + synthetic decoy graphs (unique seals)
- ONE shared sealed CONTEXT (~100k tokens) per batch
- Question forms: NL, PATH_PROG, FOLLOWUP dialog, COMPLEX (PATH3 / COUNT)

Protocol: isolated MUT batches; no decrypt; answer seals only.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter, pack_mut_batch, path_program, raw_nl_program
from oir.adapters import ceo_hq_edges, load_ceo_hq_graph

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "longctx"
KEY = b"oir-longctx-100k-v1"
SEED = 20260728
TARGET_TOKENS = 100_000
# rough: 1 token ≈ 4 chars for seal-heavy text
TARGET_CHARS = TARGET_TOKENS * 4


def estimate_tokens(text: str) -> int:
    # conservative for E-hex seals + spaces
    return max(1, len(text) // 4)


def od500_edges(path: Path, limit: int = 500) -> list[tuple[str, str, str]]:
    edges = []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows[:limit]):
        co = re.sub(r"\s+", "_", (r.get("company_name") or f"OD_{i}").strip())[:48] or f"OD_{i}"
        city = re.sub(r"\s+", "_", (r.get("city") or "Unknown").strip())[:48]
        state = re.sub(r"\s+", "_", (r.get("state") or "NA").strip())[:16]
        person = f"ODStaff_{i}"
        edges.append((person, "works_at", co))
        edges.append((co, "headquartered_in", city))
        edges.append((co, "in_state", state))
        edges.append((co, "owned_by", f"ODHold_{i}"))
        edges.append((f"ODHold_{i}", "meta_of", co))
    return edges


def pad_decoy_edges(start_i: int, n_graphs: int) -> list[tuple[str, str, str]]:
    edges = []
    for i in range(start_i, start_i + n_graphs):
        p, c, hq = f"PadPerson_{i}", f"PadCo_{i}", f"PadCity_{i}"
        edges.extend(
            [
                (p, "works_at", c),
                (c, "headquartered_in", hq),
                (c, "owned_by", f"PadHold_{i}"),
                (f"PadHold_{i}", "meta_of", c),
                (c, "partner_of", f"PadPartner_{i}"),
                (f"PadPartner_{i}", "meta_of", c),
                (f"PadDecoy_{i}", "works_at", f"PadDecoyCo_{i}"),
                (f"PadDecoyCo_{i}", "headquartered_in", f"PadDecoyCity_{i}"),
            ]
        )
    return edges


def shuffle_edges(edges: list[tuple[str, str, str]], rng: random.Random) -> list[tuple[str, str, str]]:
    e = list(edges)
    rng.shuffle(e)
    return e


def build():
    rng = random.Random(SEED)
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    wiki = graph.records
    sealer = EntitySeal(KEY)

    # --- assemble plaintext edges ---
    edges: list[tuple[str, str, str]] = []
    for r in wiki:
        edges.extend(ceo_hq_edges(r))
    od_path = ROOT / "data/real_docs/opendata500_us_companies.csv"
    if od_path.exists():
        edges.extend(od500_edges(od_path, limit=529))

    # dedupe then seal; pad until ~100k tokens
    def dedupe(edgelist):
        seen = set()
        out = []
        for e in edgelist:
            if e not in seen:
                seen.add(e)
                out.append(e)
        return out

    def render(edgelist):
        sealed = [sealer.triple(*e) for e in edgelist]
        return SealRouter(sealed).render(), sealed

    edges = dedupe(edges)
    ctx, sealed = render(edges)
    tok = estimate_tokens(ctx)
    pad_i = 0
    while tok < TARGET_TOKENS and pad_i < 20000:
        batch = 500
        edges.extend(pad_decoy_edges(pad_i, batch))
        edges = dedupe(edges)
        pad_i += batch
        # don't reseal from scratch every time — reseal only new would be faster,
        # but correctness first:
        ctx, sealed = render(edges)
        tok = estimate_tokens(ctx)
        if pad_i % 1000 == 0 or tok >= TARGET_TOKENS:
            print(f"pad_graphs={pad_i} triples={len(edges)} tokens~{tok}")

    edges = shuffle_edges(edges, rng)
    ctx, sealed = render(edges)
    tok = estimate_tokens(ctx)

    # pick quiz needles (real wiki only)
    quiz = rng.sample(wiki, 8)
    # add PATH3 needle: person → company → hq, plus meta hop variant
    # complex: COUNT works_at in ego — use SealRouter on full graph for gold

    router_full = SealRouter(sealed)
    cases = []
    nl_items = []
    prog_items = []
    follow_items = []
    complex_items = []

    for i, row in enumerate(quiz):
        person, company, hq = row["person"], row["company"], row["hq"]
        expect = sealer.atom(hq)
        co_seal = sealer.atom(company)
        p_seal = sealer.atom(person)

        # NL
        q = f"Where is the headquarters of the company that {person} works_at?"
        cid = f"LC_NL_{i}"
        nl_items.append((cid, raw_nl_program(f"QUESTION:\n{sealer.text(q)}"), ctx))
        cases.append(
            {
                "id": cid,
                "form": "NL",
                "expect": expect,
                "company_seal": co_seal,
                "person": person,
                "hq": hq,
                "q": q,
            }
        )

        # PROG
        prog = path_program(person, ("works_at", "headquartered_in"), hq).seal(sealer)
        prog.meta["start"] = p_seal
        prog.meta["rels"] = [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        cid = f"LC_PROG_{i}"
        prog_items.append((cid, prog, ctx))
        # verify gold with router
        gold = router_full.path(p_seal, [sealer.atom("works_at"), sealer.atom("headquartered_in")])
        assert expect in gold, (gold, expect, person)
        cases.append(
            {
                "id": cid,
                "form": "PROG",
                "expect": expect,
                "company_seal": co_seal,
                "person": person,
                "hq": hq,
            }
        )

        # FOLLOWUP dialog in one sealed block
        # Turn1: employer company; Turn2: HQ of that company
        t1 = f"Which company does {person} works_at?"
        t2 = "Where is that company headquartered_in?"
        body = (
            "DIALOG (multi-turn; answer FINAL turn only with HQ seal)\n"
            f"USER_1: {sealer.text(t1)}\n"
            f"USER_2: {sealer.text(t2)}\n"
            "Return the HQ seal after resolving the referent from turn 1."
        )
        cid = f"LC_FOLLOW_{i}"
        follow_items.append((cid, raw_nl_program(body), ctx))
        cases.append(
            {
                "id": cid,
                "form": "FOLLOW",
                "expect": expect,
                "company_seal": co_seal,
                "person": person,
                "hq": hq,
                "note": "sealed multi-turn; answer = HQ",
            }
        )

        # COMPLEX: PATH3 person -works_at-> co -owned_by-> Hold  (not HQ)
        # OR COUNT: how many works_at from this person (always 1) — weak
        # Better complex: person → works_at → co → headquartered_in → hq  with distractors
        # Use PATH3 via owned_by then meta_of back — answer company
        hold = f"Hold_{company}"
        prog3 = path_program(person, ("works_at", "owned_by"), hold).seal(sealer)
        prog3.meta["start"] = p_seal
        prog3.meta["rels"] = [sealer.atom("works_at"), sealer.atom("owned_by")]
        expect3 = sealer.atom(hold)
        gold3 = router_full.path(p_seal, prog3.meta["rels"])
        assert expect3 in gold3, (gold3, expect3)
        cid = f"LC_COMPLEX_{i}"
        complex_items.append((cid, prog3, ctx))
        cases.append(
            {
                "id": cid,
                "form": "COMPLEX",
                "expect": expect3,
                "company_seal": co_seal,
                "person": person,
                "target": hold,
                "kind": "PATH2_owned_by",
            }
        )

    RUNS.mkdir(parents=True, exist_ok=True)
    paths = {}
    headers = {
        "NL": f"LONG-CONTEXT sealed NL (~{tok} tok CONTEXT shared once). Multi-hop HQ.",
        "PROG": f"LONG-CONTEXT sealed PATH_PROG (~{tok} tok CONTEXT shared once).",
        "FOLLOW": f"LONG-CONTEXT sealed follow-up dialog (~{tok} tok CONTEXT shared once).",
        "COMPLEX": f"LONG-CONTEXT sealed complex PATH (~{tok} tok CONTEXT shared once).",
    }

    def pack_long(items, header: str) -> str:
        """Share one CONTEXT block; list all questions after (fits 1M windows)."""
        lines = [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
            "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>",
            "",
            header,
            "",
            "===== SHARED CONTEXT BEGIN =====",
            ctx,
            "===== SHARED CONTEXT END =====",
            "",
            "Answer EACH id below using ONLY the shared CONTEXT.",
            "",
        ]
        for cid, prog, _ in items:
            lines.append(f"##### ID {cid} #####\n{prog.body}\n")
        return "\n".join(lines)

    for form, items in [
        ("NL", nl_items),
        ("PROG", prog_items),
        ("FOLLOW", follow_items),
        ("COMPLEX", complex_items),
    ]:
        d = RUNS / f"{form}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        text = pack_long(items, headers[form])
        p = d / "BATCH.txt"
        p.write_text(text)
        paths[form] = str(p)
        print(form, "file_tokens~", estimate_tokens(text), "bytes", p.stat().st_size)

    meta = {
        "target_tokens": TARGET_TOKENS,
        "context_tokens_est": tok,
        "context_chars": len(ctx),
        "n_triples": len(edges),
        "n_wiki": len(wiki),
        "n_quiz": len(quiz),
        "pad_graphs": pad_i,
        "paths": paths,
        "cases": cases,
        "claim": (
            "Test sealed NL / PROG / FOLLOW / COMPLEX under ~100k-token sealed CONTEXT "
            "built from Wikidata + OpenData500 + pad decoys."
        ),
        "rev": sealer.rev,
        "quiz_people": [r["person"] for r in quiz],
    }
    (RESULTS / "longctx_harness.json").write_text(json.dumps(meta, indent=2))
    # also store context stats only
    (RESULTS / "longctx_stats.json").write_text(
        json.dumps(
            {
                "context_tokens_est": tok,
                "n_triples": len(edges),
                "bytes_per_batch_approx": Path(paths["PROG"]).stat().st_size,
            },
            indent=2,
        )
    )
    print(json.dumps({"context_tokens_est": tok, "n_triples": len(edges), "paths": paths}, indent=2))


if __name__ == "__main__":
    build()
