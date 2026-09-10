#!/usr/bin/env python3
"""
SEAL-Join scaled generator — multiple counterfactual twin pairs.

Each instance: randomize entity names but keep the same join pattern.
Modes: plain, sealed_handles, sealed_nohint × twins A/B.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "seal_join_scaled"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)

KEY = b"oir-seal-join-scaled-v1"
SEED = 20260724
N_INSTANCES = 8  # 8 graphs × 2 twins × 3 modes = 48 quizzes — batch by mode for LLM runs


class EntitySeal:
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
        return "".join(
            self.seal_atom(p) if re.fullmatch(r"[A-Za-z0-9_]+", p) else p for p in parts
        )


FIRST = ["Alice", "Ravi", "Nora", "Ken", "Mia", "Omar", "Priya", "Leo", "Sara", "Jon"]
CO = ["Acme", "BetaCorp", "NovaLtd", "Orbital", "PixelCo", "QuarkInc", "RidgeTech", "SummitAI"]
CITY = ["CityX", "CityY", "Harbor", "Meadow", "Cedar", "Pinnacle", "DeltaVille", "Oakport"]


def make_instance(rng: random.Random, i: int) -> dict:
    person = rng.choice(FIRST) + str(i)
    co1, co2 = rng.sample(CO, 2)
    city1, city2 = rng.sample(CITY, 2)
    other = rng.choice([p for p in FIRST if not person.startswith(p)]) + "Z" + str(i)

    edges_a = [
        (person, "works_at", co1),
        (other, "works_at", co2),
        (co1, "located_in", city1),
        (co2, "located_in", city2),
    ]
    edges_b = [
        (person, "works_at", co2),  # flip company
        (other, "works_at", co1),
        (co1, "located_in", city1),
        (co2, "located_in", city2),
    ]
    return {
        "id": f"G{i:02d}",
        "person": person,
        "answer_a": city1,
        "answer_b": city2,
        "edges_a": edges_a,
        "edges_b": edges_b,
        "query": (
            f"Where is the company located that {person} works_at? "
            "Join works_at then located_in. Answer the city only."
        ),
    }


def ctx_plain(edges):
    return "\n".join(f"{h} | {r} | {t}" for h, r, t in edges)


def ctx_sealed(sealer: EntitySeal, edges):
    return "\n".join(
        f"{sealer.seal_atom(h)} | {sealer.seal_atom(r)} | {sealer.seal_atom(t)}"
        for h, r, t in edges
    )


def write(name: str, body: str) -> str:
    p = RUNS / f"{name}.txt"
    p.write_text("MODEL UNDER TEST. No tools. No other files.\n\n=== QUIZ ===\n" + body)
    return str(p)


@dataclass
class Case:
    id: str
    graph: str
    twin: str
    mode: str
    expect: str
    expect_sealed: str
    payload: str


def build(n: int = N_INSTANCES) -> dict:
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    cases: list[Case] = []

    for i in range(n):
        inst = make_instance(rng, i)
        gid = inst["id"]
        for twin, edges, ans in [
            ("A", inst["edges_a"], inst["answer_a"]),
            ("B", inst["edges_b"], inst["answer_b"]),
        ]:
            ans_s = sealer.seal_atom(ans)
            # plain
            cases.append(Case(
                f"{gid}_{twin}_plain", gid, twin, "plain", ans, ans_s,
                write(f"{gid}_{twin}_plain", f"""
Answer using CONTEXT only. One line: ANSWER_PLAIN: <city>

QUESTION: {inst['query']}

CONTEXT:
{ctx_plain(edges)}
""".strip()),
            ))
            # sealed handles
            q_s = sealer.seal_text(inst["query"])
            cases.append(Case(
                f"{gid}_{twin}_handles", gid, twin, "handles", ans, ans_s,
                write(f"{gid}_{twin}_handles", f"""
OPAQUE JOIN — no decryption. Same entity ⇒ same seal.

Join:
1. Triple with HEAD={sealer.seal_atom(inst['person'])} and REL={sealer.seal_atom('works_at')} → company C
2. Triple with HEAD=C and REL={sealer.seal_atom('located_in')} → city
3. ANSWER_SEALED: <city seal>

QUESTION:
{q_s}

CONTEXT:
{ctx_sealed(sealer, edges)}
""".strip()),
            ))
            # sealed nohint
            cases.append(Case(
                f"{gid}_{twin}_nohint", gid, twin, "nohint", ans, ans_s,
                write(f"{gid}_{twin}_nohint", f"""
Opaque sealed triples. No decryption.

QUESTION:
{q_s}

CONTEXT:
{ctx_sealed(sealer, edges)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
""".strip()),
            ))

    harness = {
        "n_instances": n,
        "n_cases": len(cases),
        "rev": sealer.rev,
        "cases": [asdict(c) for c in cases],
    }
    (RESULTS / "seal_join_scaled_harness.json").write_text(json.dumps(harness, indent=2))
    # batched prompts by mode for efficient LLM runs
    for mode in ("plain", "handles", "nohint"):
        subset = [c for c in cases if c.mode == mode]
        lines = [
            "MODEL UNDER TEST. No tools. Answer EVERY item. One ANSWER line per ID.\n",
            "For plain mode: ANSWER_PLAIN[<id>]: <city>",
            "For sealed modes: ANSWER_SEALED[<id>]: <seal> or UNKNOWN\n",
        ]
        for c in subset:
            quiz = Path(c.payload).read_text().split("=== QUIZ ===\n", 1)[1]
            lines.append(f"\n##### ID {c.id} #####\n{quiz}\n")
        (RUNS / f"BATCH_{mode}.txt").write_text("\n".join(lines))

    print(f"scaled SEAL-Join: {n} graphs, {len(cases)} cases")
    print("batches:", list(RUNS.glob("BATCH_*.txt")))
    return harness


if __name__ == "__main__":
    build()
