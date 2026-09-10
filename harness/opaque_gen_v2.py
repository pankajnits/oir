#!/usr/bin/env python3
"""
Opaque Generation v2 — mechanism-driven solution attempt.

Theory (from lit + LLM internals)
---------------------------------
1. Induction heads (Olsson et al. 2022): transformers excel at match-and-copy
   [A][B]…[A]→[B], not at semantic search over unfamiliar tokens.
2. Ciphered reasoning (ACL/ICLR 2025–26 "All Code, No Thought"): models can
   often *translate* ciphers but fail to *reason* inside them. So do NOT ask
   for sealed CoT — ask for sealed COPY from retrieved spans.
3. NUMEN (2026): char n-gram hashing recovers morphology (caregiver/caregivers)
   without stemming — works under deterministic hash/seal.
4. FHE/PRAG: orthogonal crypto privacy — not our capability claim.

Architecture (opaque at QUERY time; ingest may see plaintext once)
------------------------------------------------------------------
  INGEST: chunk C → word seals + char-ngram seals → inverted IDF index
  QUERY:  seal Q (+ ngrams + syn legend) → BM25-like over seal postings
          → top-k sealed passages (word-sealed text only)
  GENERATE: induction-friendly prompt (DEMO of copy + STRUCT lines)
            → ANSWER_SEALED from retrieved tokens only

NO gold answer lines. NO cleartext reader of C at query time.
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oir import EntitySeal  # noqa: E402

# Reuse cases/docs from subjective harness
from harness.subjective_oir import (  # noqa: E402
    DOCS,
    FETA,
    SUBJECTIVE_CASES,
    SYN_GROUPS,
    load_feta,
    prep_for_seal,
    seal_text,
)

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "opaque_v2"
KEY = b"oir-opaque-v2"
SEED = 20260728
TOP_K = 5
NGRAM_NS = (3, 4, 5)


# ---------------------------------------------------------------------------
# Sealed n-gram features (NUMEN-inspired, HMAC seals)
# ---------------------------------------------------------------------------


def char_ngrams(word: str, ns: tuple[int, ...] = NGRAM_NS) -> list[str]:
    w = f"^{word.lower()}$"
    out = []
    for n in ns:
        if len(w) < n:
            continue
        for i in range(len(w) - n + 1):
            out.append(w[i : i + n])
    return out


def words_of(plain: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_.\-]*", prep_for_seal(plain))


@dataclass
class Chunk:
    cid: str
    plain: str
    sealed_text: str
    word_seals: set[str] = field(default_factory=set)
    feat_seals: set[str] = field(default_factory=set)  # words + ngrams + syn mates


@dataclass
class SealIndex:
    """Inverted index over sealed features. Query uses seals only."""

    chunks: list[Chunk]
    postings: dict[str, list[tuple[int, float]]]  # feat → [(chunk_i, tf)]
    df: Counter
    n_chunks: int
    sealer: EntitySeal

    def score(self, query_feats: set[str], k: int) -> list[tuple[float, Chunk]]:
        scores: dict[int, float] = defaultdict(float)
        for f in query_feats:
            if f not in self.postings:
                continue
            idf = math.log(1.0 + self.n_chunks / (1.0 + self.df[f]))
            for ci, tf in self.postings[f]:
                # BM25-lite
                scores[ci] += idf * (tf / (tf + 1.2))
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:k]
        return [(sc, self.chunks[i]) for i, sc in ranked]


def feat_seals_for_text(sealer: EntitySeal, plain: str, expand_syn: bool = True) -> set[str]:
    """Build opaque retrieval features from plaintext at ingest/query-seal time."""
    feats: set[str] = set()
    ws = words_of(plain)
    for w in ws:
        feats.add(sealer.atom(w))
        for ng in char_ngrams(w):
            feats.add(sealer.atom(f"ng:{ng}"))
    if expand_syn:
        wset = set(ws)
        for group in SYN_GROUPS:
            if wset & set(group):
                for g in group:
                    gw = prep_for_seal(g)
                    feats.add(sealer.atom(gw))
                    for ng in char_ngrams(gw):
                        feats.add(sealer.atom(f"ng:{ng}"))
    return feats


def chunk_document(doc_id: str, plain: str, sealer: EntitySeal) -> list[Chunk]:
    """Passage chunks: paragraphs + sliding 2-line windows (ingest only)."""
    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    raw_chunks: list[str] = []
    # paragraphs separated by blank in original — fall back to single lines + pairs
    buf = []
    for ln in plain.splitlines():
        if not ln.strip():
            if buf:
                raw_chunks.append("\n".join(buf))
                buf = []
        else:
            buf.append(ln.strip())
    if buf:
        raw_chunks.append("\n".join(buf))
    # add overlapping line pairs for denser evidence
    for i in range(len(lines) - 1):
        pair = lines[i] + "\n" + lines[i + 1]
        if pair not in raw_chunks:
            raw_chunks.append(pair)
    # singleton fact-ish lines
    for ln in lines:
        if len(ln) > 20 and ln not in raw_chunks:
            raw_chunks.append(ln)

    out = []
    seen = set()
    for j, text in enumerate(raw_chunks):
        key = text.strip()
        if key in seen or len(key) < 15:
            continue
        seen.add(key)
        sealed = seal_text(sealer, text)
        ws = {sealer.atom(w) for w in words_of(text)}
        feats = feat_seals_for_text(sealer, text, expand_syn=True)
        out.append(
            Chunk(
                cid=f"{doc_id}#{j}",
                plain=text,
                sealed_text=sealed,
                word_seals=ws,
                feat_seals=feats,
            )
        )
    return out


def build_index(chunks: list[Chunk], sealer: EntitySeal) -> SealIndex:
    postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
    df: Counter = Counter()
    for i, ch in enumerate(chunks):
        tf = Counter(ch.feat_seals)
        for f, c in tf.items():
            postings[f].append((i, float(c)))
            df[f] += 1
    return SealIndex(
        chunks=chunks,
        postings=dict(postings),
        df=df,
        n_chunks=len(chunks),
        sealer=sealer,
    )


def sealed_syn_legend(sealer: EntitySeal) -> str:
    lines = []
    for group in SYN_GROUPS:
        seals = [sealer.atom(prep_for_seal(w)) for w in group]
        lines.append("SYN: " + " ~ ".join(seals))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompts: exploit induction / copy, not sealed CoT
# ---------------------------------------------------------------------------


def induction_demo(sealer: EntitySeal) -> str:
    """Tiny sealed copy demo (unrelated content) to activate induction heads."""
    # Use fixed toy facts sealed with same key so format is learnable
    q = seal_text(sealer, "What is the color code?")
    span = seal_text(sealer, "Color code: amber lattice seven.")
    ans = seal_text(sealer, "amber lattice seven")
    return (
        "DEMO (copy pattern — do the same on the real item):\n"
        f"QUESTION: {q}\n"
        f"R1: {span}\n"
        f"ANSWER_SEALED: {ans}\n"
        "Rule: answer tokens must appear in some R-line."
    )


def pack_sr_prompt(
    cid: str,
    q_sealed: str,
    retrieved: list[Chunk],
    legend: str,
    demo: str,
) -> str:
    rblock = "\n".join(f"R{i}: {ch.sealed_text}" for i, ch in enumerate(retrieved, 1))
    if not retrieved:
        rblock = "(empty retrieve)"
    return (
        "OPAQUE GENERATION — copy from retrieved seals (no decrypt, no sealed CoT).\n"
        "Mechanism: match QUESTION seals to R-lines; COPY supporting sealed spans into answer.\n"
        f"{demo}\n\n"
        f"SEALED_SYN_LEGEND:\n{legend}\n\n"
        f"QUESTION:\n{q_sealed}\n\n"
        f"RETRIEVED:\n{rblock}\n\n"
        f"Reply ONLY:\n"
        f"EVIDENCE_SEALED[{cid}]: <R-lines used joined by ||>\n"
        f"ANSWER_SEALED[{cid}]: <sealed tokens copied from those R-lines>"
    )


def pack_nl_prompt(cid: str, q_sealed: str, ctx: str) -> str:
    return (
        "OPAQUE GENERATION control — full sealed CONTEXT.\n"
        f"QUESTION:\n{q_sealed}\n\nCONTEXT:\n{ctx}\n\n"
        f"ANSWER_SEALED[{cid}]: <sealed answer> or UNKNOWN"
    )


# ---------------------------------------------------------------------------
# Build + ablations
# ---------------------------------------------------------------------------


def gold_hit(retrieved: list[Chunk], evid_sealed: list[str]) -> float:
    if not evid_sealed:
        return 0.0
    blob = " ".join(ch.sealed_text for ch in retrieved)
    hits = 0
    for g in evid_sealed:
        gtoks = re.findall(r"E[0-9a-f]{12}", g)
        if gtoks and sum(1 for t in gtoks if t in blob) / len(gtoks) >= 0.55:
            hits += 1
    return hits / len(evid_sealed)


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    feta = load_feta(6, rng)
    cases_spec = SUBJECTIVE_CASES + feta

    # INGEST: build per-doc sealed indexes (plaintext once)
    doc_chunks: dict[str, list[Chunk]] = {}
    doc_index: dict[str, SealIndex] = {}
    doc_ctx_sealed: dict[str, str] = {}
    for did, plain in DOCS.items():
        chs = chunk_document(did, plain, sealer)
        doc_chunks[did] = chs
        doc_index[did] = build_index(chs, sealer)
        doc_ctx_sealed[did] = seal_text(sealer, plain)

    legend = sealed_syn_legend(sealer)
    demo = induction_demo(sealer)

    nl_items, v2_items, cases = [], [], []
    for spec in cases_spec:
        if spec["doc"] == "feta":
            plain_ctx = spec["context_plain"]
            chs = chunk_document(spec["id"], plain_ctx, sealer)
            index = build_index(chs, sealer)
            ctx_sealed = seal_text(sealer, plain_ctx)
        else:
            index = doc_index[spec["doc"]]
            ctx_sealed = doc_ctx_sealed[spec["doc"]]

        evid_sealed = [seal_text(sealer, e) for e in spec["gold_evidence_plain"]]
        q_sealed = seal_text(sealer, spec["question"])
        q_feats = feat_seals_for_text(sealer, spec["question"], expand_syn=True)
        ranked = index.score(q_feats, TOP_K)
        retrieved = [ch for _, ch in ranked]
        hit = gold_hit(retrieved, evid_sealed)

        cid_nl = f"{spec['id']}_NL"
        cid_v2 = f"{spec['id']}_V2"

        nl_items.append((cid_nl, pack_nl_prompt(cid_nl, q_sealed, ctx_sealed)))
        v2_items.append(
            (
                cid_v2,
                pack_sr_prompt(cid_v2, q_sealed, retrieved, legend, demo),
            )
        )
        cases.append(
            {
                "id_nl": cid_nl,
                "id_v2": cid_v2,
                "doc": spec["doc"],
                "question": spec["question"],
                "gold_evidence_plain": spec["gold_evidence_plain"],
                "gold_evidence_sealed": evid_sealed,
                "rubric_must": spec["rubric_must"],
                "opaque_retrieve_gold_hit": round(hit, 3),
                "n_retrieved": len(retrieved),
                "retrieve_scores": [round(s, 4) for s, _ in ranked],
                "retrieved_preview": [ch.plain[:80] for ch in retrieved],
            }
        )

    def pack(name, header, items):
        d = RUNS / f"{name}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        lines = [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
            header,
            "",
        ]
        for cid, body in items:
            lines.append(f"##### ID {cid} #####\n{body}\n")
        (d / "BATCH.txt").write_text("\n".join(lines))
        return str(d / "BATCH.txt")

    mean_hit = sum(c["opaque_retrieve_gold_hit"] for c in cases) / max(1, len(cases))
    policy = [c for c in cases if c["doc"] != "feta"]
    feta_c = [c for c in cases if c["doc"] == "feta"]
    harness = {
        "n": len(cases),
        "theory": [
            "induction heads → copy not sealed CoT",
            "ciphered reasoning lit → avoid reasoning-in-seals",
            "NUMEN n-gram hash → morphology under seals",
            "ingest plaintext OK; query opaque",
        ],
        "paths": {
            "NL": pack("NL", "Full sealed C control.", nl_items),
            "V2_NGRAM_COPY": pack(
                "V2_NGRAM_COPY",
                "Opaque n-gram seal-IR + induction DEMO copy generate.",
                v2_items,
            ),
        },
        "cases": cases,
        "rev": sealer.rev,
        "opaque_retrieve_mean_gold_hit": round(mean_hit, 3),
        "policy_mean_gold_hit": round(
            sum(c["opaque_retrieve_gold_hit"] for c in policy) / max(1, len(policy)), 3
        ),
        "feta_mean_gold_hit": round(
            sum(c["opaque_retrieve_gold_hit"] for c in feta_c) / max(1, len(feta_c)), 3
        ),
        "claim": (
            "Opaque gen v2: sealed char-ngram BM25 retrieve + induction-copy generate. "
            "No gold lines. No cleartext C at query."
        ),
    }
    (RESULTS / "opaque_v2_harness.json").write_text(json.dumps(harness, indent=2))
    print(
        json.dumps(
            {
                "n": len(cases),
                "mean_gold_hit": harness["opaque_retrieve_mean_gold_hit"],
                "policy_hit": harness["policy_mean_gold_hit"],
                "feta_hit": harness["feta_mean_gold_hit"],
                "paths": harness["paths"],
            },
            indent=2,
        )
    )
    for c in cases:
        print(
            f"  {c['id_v2']:18} hit={c['opaque_retrieve_gold_hit']} "
            f"top={c['retrieved_preview'][0][:50] if c['retrieved_preview'] else 'NONE'}..."
        )


if __name__ == "__main__":
    build()
