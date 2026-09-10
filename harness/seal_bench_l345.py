#!/usr/bin/env python3
"""
SEAL-Bench ladder L3–L5 (scrutiny + novelty beyond 2-hop join).

L3: 3-hop path  person → works_at → co → owned_by → parent → HQ_in → city
L4: distractor density — many fake edges; target path unique
L5: binder stress — repeated intermediate seal must bind across branches
    (conjunctive: find city where BOTH Alice and Bob's companies are located —
     only valid if they share a city; twin flips so only one twin has shared city)

Also emits twin multiset diagnostics (do A/B share the same bag of endpoint atoms?).
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
RUNS = ROOT / "runs" / "seal_bench_l345"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)

KEY = b"oir-seal-bench-l345-v1"
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

    def text(self, s: str) -> str:
        return "".join(
            self.atom(p) if re.fullmatch(r"[A-Za-z0-9_]+", p) else p
            for p in re.findall(r"[A-Za-z0-9_]+|[^A-Za-z0-9_]+", s)
        )


def bag(edges):
    b = []
    for h, r, t in edges:
        b.extend([h, r, t])
    return tuple(sorted(b))


def render(sealer: EntitySeal, edges, sealed=True):
    if sealed:
        return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)
    return "\n".join(f"{h} | {r} | {t}" for h, r, t in edges)


def write(name, body):
    p = RUNS / f"{name}.txt"
    p.write_text("MODEL UNDER TEST. No tools. No other files.\n\n=== QUIZ ===\n" + body)
    return str(p)


@dataclass
class Case:
    id: str
    level: str
    twin: str
    mode: str
    expect: str
    expect_sealed: str
    payload: str
    meta: dict


def build_l3(sealer, rng, i):
    """3-hop: person works_at co; co owned_by parent; parent HQ_in city"""
    person = f"P{i}"
    co, co2 = f"Co{i}A", f"Co{i}B"
    par, par2 = f"Par{i}A", f"Par{i}B"
    city, city2 = f"City{i}A", f"City{i}B"
    edges_a = [
        (person, "works_at", co),
        (co, "owned_by", par),
        (par, "HQ_in", city),
        # distractors
        (person + "x", "works_at", co2),
        (co2, "owned_by", par2),
        (par2, "HQ_in", city2),
    ]
    edges_b = [
        (person, "works_at", co2),
        (co2, "owned_by", par2),
        (par2, "HQ_in", city2),
        (person + "x", "works_at", co),
        (co, "owned_by", par),
        (par, "HQ_in", city),
    ]
    q = f"What city is the HQ of the parent company that owns the company where {person} works_at? Answer city only."
    return edges_a, edges_b, q, city, city2, {
        "hops": 3,
        "bag_equal": bag(edges_a) == bag(edges_b),
        "bag_a": list(bag(edges_a)),
        "bag_b": list(bag(edges_b)),
    }


def build_l4(sealer, rng, i):
    """2-hop with heavy distractors"""
    person = f"Q{i}"
    co, co2, co3 = f"R{i}", f"S{i}", f"T{i}"
    city, city2, city3 = f"U{i}", f"V{i}", f"W{i}"
    edges_a = [
        (person, "works_at", co),
        (co, "located_in", city),
    ]
    # many distractors
    for j in range(12):
        edges_a.append((f"Dx{i}_{j}", "works_at", f"Dco{i}_{j}"))
        edges_a.append((f"Dco{i}_{j}", "located_in", f"Dci{i}_{j}"))
    edges_a += [
        (co2, "located_in", city2),
        (co3, "located_in", city3),
        (f"Z{i}", "works_at", co2),
    ]
    # twin: flip person's company
    edges_b = [(h, r, t) for h, r, t in edges_a]
    edges_b = [(person, "works_at", co2) if (h == person and r == "works_at") else (h, r, t) for h, r, t in edges_b]
    # ensure co2 located_in city2 exists
    q = f"Where is the company located that {person} works_at? City only."
    return edges_a, edges_b, q, city, city2, {"distractors": 12, "bag_equal": bag(edges_a) == bag(edges_b)}


def build_l5(sealer, rng, i):
    """
    Binder: city where BOTH Alice and Bob work (companies share located_in).
    Twin A: Alice@Co1, Bob@Co2, both Cos in SharedCity
    Twin B: Alice@Co1 in CityA, Bob@Co2 in CityB — no shared city → expect UNKNOWN
    """
    a, b = f"A{i}", f"B{i}"
    co1, co2 = f"C1_{i}", f"C2_{i}"
    shared, cA, cB = f"Shared{i}", f"SoloA{i}", f"SoloB{i}"
    edges_a = [
        (a, "works_at", co1),
        (b, "works_at", co2),
        (co1, "located_in", shared),
        (co2, "located_in", shared),
    ]
    edges_b = [
        (a, "works_at", co1),
        (b, "works_at", co2),
        (co1, "located_in", cA),
        (co2, "located_in", cB),
    ]
    q = (
        f"Find the city where BOTH {a} and {b} have their companies located_in "
        f"(companies may differ). If none, UNKNOWN. Answer city seal/plain only."
    )
    return edges_a, edges_b, q, shared, "UNKNOWN", {
        "binder": True,
        "twin_b_is_unknown": True,
        "bag_equal": bag(edges_a) == bag(edges_b),
    }


def make_cases():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    cases: list[Case] = []

    builders = [("L3", build_l3), ("L4", build_l4), ("L5", build_l5)]
    for level, builder in builders:
        for i in range(4):  # 4 instances per level
            edges_a, edges_b, q, ans_a, ans_b, meta = builder(sealer, rng, i)
            for twin, edges, ans in [("A", edges_a, ans_a), ("B", edges_b, ans_b)]:
                exp_s = "UNKNOWN" if ans == "UNKNOWN" else sealer.atom(ans)
                # plain
                cases.append(Case(
                    f"{level}_G{i}_{twin}_plain", level, twin, "plain", ans, exp_s,
                    write(f"{level}_G{i}_{twin}_plain", f"""
Answer from CONTEXT triples. One line: ANSWER_PLAIN: <city_or_UNKNOWN>

QUESTION: {q}

CONTEXT:
{render(sealer, edges, sealed=False)}
""".strip()),
                    meta,
                ))
                # handles
                if level == "L3":
                    handles = f"""
Handles (opaque):
person={sealer.atom(f'P{i}')}
works_at={sealer.atom('works_at')}
owned_by={sealer.atom('owned_by')}
HQ_in={sealer.atom('HQ_in')}
Join person-works_at→co ; co-owned_by→parent ; parent-HQ_in→city.
"""
                elif level == "L4":
                    person = f"Q{i}"
                    handles = f"""
Handles: person={sealer.atom(person)} works_at={sealer.atom('works_at')} located_in={sealer.atom('located_in')}
Join person-works_at→co ; co-located_in→city. Ignore distractors.
"""
                else:
                    handles = f"""
Handles: A={sealer.atom(f'A{i}')} B={sealer.atom(f'B{i}')}
works_at={sealer.atom('works_at')} located_in={sealer.atom('located_in')}
Find companies for A and B; find located_in cities; if same city return it else UNKNOWN.
"""
                cases.append(Case(
                    f"{level}_G{i}_{twin}_handles", level, twin, "handles", ans, exp_s,
                    write(f"{level}_G{i}_{twin}_handles", f"""
OPAQUE JOIN — no decryption. Same entity ⇒ same seal.
{handles}
QUESTION:
{sealer.text(q)}

CONTEXT:
{render(sealer, edges, sealed=True)}

Reply: ANSWER_SEALED: <seal> OR UNKNOWN
""".strip()),
                    meta,
                ))

    harness = {
        "levels": ["L3", "L4", "L5"],
        "n_cases": len(cases),
        "rev": sealer.rev,
        "cases": [asdict(c) for c in cases],
    }
    (RESULTS / "seal_bench_l345_harness.json").write_text(json.dumps(harness, indent=2))

    # batches by level×mode
    for level in ["L3", "L4", "L5"]:
        for mode in ["plain", "handles"]:
            subset = [c for c in cases if c.level == level and c.mode == mode]
            lines = ["MODEL UNDER TEST. No tools. Answer EVERY ID. One answer line per ID.\n"]
            if mode == "plain":
                lines.append("Format: ANSWER_PLAIN[<id>]: <city_or_UNKNOWN>\n")
            else:
                lines.append("Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n")
            for c in subset:
                quiz = Path(c.payload).read_text().split("=== QUIZ ===\n", 1)[1]
                lines.append(f"\n##### ID {c.id} #####\n{quiz}\n")
            (RUNS / f"BATCH_{level}_{mode}.txt").write_text("\n".join(lines))

    print(f"L3–L5 cases: {len(cases)}")
    for level in ["L3", "L4", "L5"]:
        print(level, "plain", sum(1 for c in cases if c.level == level and c.mode == "plain"),
              "handles", sum(1 for c in cases if c.level == level and c.mode == "handles"))
    return harness


if __name__ == "__main__":
    make_cases()
