#!/usr/bin/env python3
"""
SEAL-Join — counterfactual twin benchmark (Phase 3 core).

Goal
----
Tasks reviewers cannot dismiss as string-find:
  - Conjunctive join over a repeated intermediate seal
  - Twin graphs with SAME seal multiset / similar surface form
  - DIFFERENT edge wiring ⇒ DIFFERENT answers
  - Plaintext ceiling vs sealed free-join vs scaffolded join

Seal choice
-----------
Entity/word HMAC (not per-char): we already know char-HMAC fails script crypto.
Here we measure *reasoning under isomorphism*, not confidentiality theater.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "seal_join"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

KEY = b"oir-seal-join-key-v1"


class EntitySeal:
    """Deterministic per-entity (word) HMAC seals."""

    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def seal_atom(self, atom: str) -> str:
        if atom not in self.fwd:
            dig = hmac.new(self.key, atom.encode(), hashlib.sha256).digest()
            tok = "E" + dig[:6].hex()
            self.fwd[atom] = tok
            self.rev[tok] = atom
        return self.fwd[atom]

    def seal_text(self, text: str) -> str:
        parts = re.findall(r"[A-Za-z0-9_]+|[^A-Za-z0-9_]+", text)
        out = []
        for p in parts:
            if re.fullmatch(r"[A-Za-z0-9_]+", p):
                out.append(self.seal_atom(p))
            else:
                out.append(p)
        return "".join(out)

    def unseal(self, text: str) -> str:
        out = text
        for tok, w in sorted(self.rev.items(), key=lambda kv: -len(kv[0])):
            out = out.replace(tok, w)
        return out


def edges_to_context(sealer: EntitySeal, edges: list[tuple[str, str, str]]) -> str:
    """Render as sealed triples: HEAD | REL | TAIL"""
    lines = []
    for h, r, t in edges:
        lines.append(
            f"{sealer.seal_atom(h)} | {sealer.seal_atom(r)} | {sealer.seal_atom(t)}"
        )
    return "\n".join(lines)


# Twin graphs: same nodes & relations vocabulary; different wiring
NODES = ["Alice", "Bob", "Carol", "Acme", "BetaCorp", "CityX", "CityY"]
RELS = ["works_at", "located_in", "reports_to"]

# Twin A: Alice works_at Acme; Acme located_in CityX → join answer CityX
EDGES_A = [
    ("Alice", "works_at", "Acme"),
    ("Bob", "works_at", "BetaCorp"),
    ("Carol", "works_at", "Acme"),
    ("Acme", "located_in", "CityX"),
    ("BetaCorp", "located_in", "CityY"),
    ("Alice", "reports_to", "Carol"),
]

# Twin B: same edge COUNT and same endpoint multiset as much as possible,
# but Alice's company is in CityY
EDGES_B = [
    ("Alice", "works_at", "BetaCorp"),  # flipped
    ("Bob", "works_at", "Acme"),        # flipped
    ("Carol", "works_at", "Acme"),
    ("Acme", "located_in", "CityX"),
    ("BetaCorp", "located_in", "CityY"),
    ("Alice", "reports_to", "Carol"),
]

QUERY_PLAIN = (
    "Where is the company located that Alice works_at? "
    "Join works_at then located_in. Answer the city only."
)
ANSWER_A = "CityX"
ANSWER_B = "CityY"


@dataclass
class Case:
    id: str
    twin: str
    mode: str  # plain | sealed_free | sealed_scaffold
    expect: str
    payload: str


def write(pid: str, body: str) -> str:
    p = RUNS / f"{pid}.txt"
    p.write_text("MODEL UNDER TEST. No tools. No other files.\n\n=== QUIZ ===\n" + body)
    return str(p)


def build() -> dict:
    sa = EntitySeal(KEY)
    ctx_a = edges_to_context(sa, EDGES_A)
    ctx_b = edges_to_context(sa, EDGES_B)
    q_sealed = sa.seal_text(QUERY_PLAIN)

    # Verify twins share similar seal bags
    def bag(edges):
        b = []
        for h, r, t in edges:
            b.extend([h, r, t])
        return sorted(b)

    cases: list[Case] = []

    # Plaintext ceilings
    for twin, edges, ans in [("A", EDGES_A, ANSWER_A), ("B", EDGES_B, ANSWER_B)]:
        plain_ctx = "\n".join(f"{h} | {r} | {t}" for h, r, t in edges)
        cases.append(Case(
            f"SJ_plain_{twin}",
            twin,
            "plain",
            ans,
            write(f"SJ_plain_{twin}", f"""
Answer using CONTEXT triples only. Reply one line: ANSWER_PLAIN: <city>

QUESTION: {QUERY_PLAIN}

CONTEXT (HEAD | REL | TAIL):
{plain_ctx}
""".strip()),
        ))

    # Sealed free join
    for twin, ctx, ans in [("A", ctx_a, ANSWER_A), ("B", ctx_b, ANSWER_B)]:
        cases.append(Case(
            f"SJ_sealed_free_{twin}",
            twin,
            "sealed_free",
            ans,
            write(f"SJ_sealed_free_{twin}", f"""
OPAQUE JOIN PROTOCOL — no decryption

CONTEXT triples are entity-HMAC seals: HEAD | REL | TAIL
Same entity ⇒ same seal. You cannot invert seals.

Join rule (structure only):
1. Find triple where HEAD seal matches Alice's seal and REL is works_at.
2. Take that TAIL seal as company C.
3. Find triple where HEAD is C and REL is located_in.
4. Return that TAIL seal as ANSWER_SEALED (city).

If impossible: UNKNOWN

QUESTION (sealed):
{q_sealed}

Alice seal (opaque identity handle): {sa.seal_atom("Alice")}
works_at seal: {sa.seal_atom("works_at")}
located_in seal: {sa.seal_atom("located_in")}

CONTEXT:
{ctx}

Reply: ANSWER_SEALED: <city seal> OR UNKNOWN
""".strip()),
        ))

    # Counterfactual twin stress: same prompt template, must not give A's answer for B
    # (already covered by separate A/B)

    # Sealed without relation name hints (harder) — only sealed question
    cases.append(Case(
        "SJ_sealed_nohint_A",
        "A",
        "sealed_nohint",
        ANSWER_A,
        write("SJ_sealed_nohint_A", f"""
Opaque sealed triples. No decryption. Same entity ⇒ same seal.

QUESTION:
{q_sealed}

CONTEXT:
{ctx_a}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
""".strip()),
    ))
    cases.append(Case(
        "SJ_sealed_nohint_B",
        "B",
        "sealed_nohint",
        ANSWER_B,
        write("SJ_sealed_nohint_B", f"""
Opaque sealed triples. No decryption. Same entity ⇒ same seal.

QUESTION:
{q_sealed}

CONTEXT:
{ctx_b}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
""".strip()),
    ))

    harness = {
        "benchmark": "SEAL-Join",
        "answer_A": ANSWER_A,
        "answer_B": ANSWER_B,
        "sealed_A": sa.seal_atom(ANSWER_A),
        "sealed_B": sa.seal_atom(ANSWER_B),
        "alice": sa.seal_atom("Alice"),
        "rev": sa.rev,
        "node_bag_A": bag(EDGES_A),
        "node_bag_B": bag(EDGES_B),
        "cases": [asdict(c) for c in cases],
    }
    (RESULTS / "seal_join_harness.json").write_text(json.dumps(harness, indent=2))
    (RUNS / "index.json").write_text(
        json.dumps({"n": len(cases), "ids": [c.id for c in cases]}, indent=2)
    )
    print(f"SEAL-Join: {len(cases)} cases")
    print("CityX seal:", sa.seal_atom(ANSWER_A))
    print("CityY seal:", sa.seal_atom(ANSWER_B))
    for c in cases:
        print(f"  {c.id:24} twin={c.twin} mode={c.mode} expect={c.expect}")
    return harness


if __name__ == "__main__":
    build()
