#!/usr/bin/env python3
"""
NL → sealed path-program compiler stack eval (goal-aligned OIR).

Conditions:
  RAW   — seal NL question verbatim (baseline 1-hop fail mode)
  COMP  — PathCompiler → sealed PATH_QUERY (same encoding)
  TWIN  — COMP on counterfactual employer wiring (must flip HQ)
  PROBE — sealed NL; force MID + ANSWER (diagnose 1-hop stop)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from nl_to_path_compiler import DEFAULT_TEMPLATES, PathCompiler  # noqa: E402

DATA = json.loads((ROOT / "data/real/wikidata_ceo_hops_v2.json").read_text())
RESULTS = ROOT / "results"
RUNS = ROOT / "runs"
KEY = b"oir-compiler-stack-v1"
SEED = 20260727


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


def render(sealer: EntitySeal, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def build_edges(person, company, hq, decoy, twin_company=None, twin_hq=None):
    """Ambiguous multi-sink graph. Twin rewires person→decoy employer."""
    co = twin_company or company
    city = twin_hq or hq
    dco, dhq = decoy["company"], decoy["hq"]
    # In twin mode co==dco; keep a distinct distractor company for ambiguity.
    if co == dco:
        # pick distractor from original company if available
        dist_co, dist_hq = company, hq
    else:
        dist_co, dist_hq = dco, dhq
    hold, part = f"Hold_{co}", f"Part_{co}"
    edges = [
        (person, "works_at", co),
        (co, "headquartered_in", city),
        (dist_co, "headquartered_in", dist_hq),
        (co, "owned_by", hold),
        (hold, "meta_of", f"Meta_{co}"),
        (co, "partner_of", part),
        (part, "meta_of", f"PMeta_{co}"),
        (f"DecoyPerson_{dist_co}", "works_at", dist_co),
    ]
    # dedupe while preserving order
    seen, out = set(), []
    for e in edges:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def write_batch(dirname: str, header: str, items: list[tuple[str, str]]):
    d = RUNS / dirname
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "Same encoding on question and context. No external world knowledge.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        header + "\n",
    ]
    for cid, body in items:
        lines.append(f"\n##### ID {cid} #####\n{body}\n")
    path = d / "BATCH.txt"
    path.write_text("\n".join(lines))
    return str(path)


def main():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    for r in ("works_at", "headquartered_in", "owned_by", "partner_of", "meta_of"):
        sealer.atom(r)

    pool = []
    seen = set()
    for r in DATA:
        if r["person"] in seen or re.match(r"^Q\d+$", r["person"]):
            continue
        seen.add(r["person"])
        pool.append(r)
    assert len(pool) >= 20, len(pool)

    lexicon = {r["person"] for r in pool}
    compiler = PathCompiler(lexicon)

    quiz = pool[:12]
    cases = []
    raw_items, comp_items, twin_items, probe_items = [], [], [], []

    for i, row in enumerate(quiz):
        decoy = rng.choice([r for r in pool if r["company"] != row["company"]])
        person, company, hq = row["person"], row["company"], row["hq"]
        tmpl = DEFAULT_TEMPLATES[i % len(DEFAULT_TEMPLATES)]
        nl = tmpl.format(person=person if i % 2 == 0 else person.replace("_", " "))

        edges = build_edges(person, company, hq, decoy)
        ctx = render(sealer, edges)
        exp = sealer.atom(hq)
        mid = sealer.atom(company)

        cid_r = f"CMP_RAW_{i}"
        raw_items.append((cid_r, f"QUESTION:\n{sealer.text(nl)}\n\nCONTEXT:\n{ctx}"))
        cases.append(
            {
                "id": cid_r,
                "cond": "raw_sealed_nl",
                "nl": nl,
                "expect": exp,
                "intermediate_company": mid,
                "plain_hq": hq,
                "person": person,
            }
        )

        cr = compiler.compile(nl)
        assert cr.ok, (nl, cr)
        prog_sealed = compiler.seal_program(person, sealer.atom)

        cid_c = f"CMP_COMP_{i}"
        comp_items.append((cid_c, f"{prog_sealed}\n\nCONTEXT:\n{ctx}"))
        cases.append(
            {
                "id": cid_c,
                "cond": "compiled_path",
                "nl": nl,
                "compile": cr.to_dict(),
                "expect": exp,
                "intermediate_company": mid,
                "plain_hq": hq,
                "person": person,
            }
        )

        edges_t = build_edges(
            person, company, hq, decoy, twin_company=decoy["company"], twin_hq=decoy["hq"]
        )
        ctx_t = render(sealer, edges_t)
        exp_t = sealer.atom(decoy["hq"])
        cid_t = f"CMP_TWIN_{i}"
        twin_items.append((cid_t, f"{prog_sealed}\n\nCONTEXT:\n{ctx_t}"))
        cases.append(
            {
                "id": cid_t,
                "cond": "compiled_twin",
                "nl": nl,
                "expect": exp_t,
                "plain_hq": decoy["hq"],
                "person": person,
                "twin_company": decoy["company"],
                "original_hq": hq,
                "original_expect": exp,
            }
        )

        cid_p = f"CMP_PROBE_{i}"
        probe_items.append(
            (
                cid_p,
                f"QUESTION:\n{sealer.text(nl)}\n\nCONTEXT:\n{ctx}\n\n"
                f"Reply exactly:\n"
                f"MID_SEALED[{cid_p}]: <seal>\n"
                f"ANSWER_SEALED[{cid_p}]: <seal>\n"
                f"(MID = first hop tail; ANSWER = final location)",
            )
        )
        cases.append(
            {
                "id": cid_p,
                "cond": "probe_mid_final",
                "nl": nl,
                "expect": exp,
                "expect_mid": mid,
                "plain_hq": hq,
                "person": person,
            }
        )

    write_batch("compiler_raw_ONLY", "RAW: sealed NL question (baseline).", raw_items)
    write_batch("compiler_comp_ONLY", "COMPILED: sealed path program from NL compiler.", comp_items)
    write_batch("compiler_twin_ONLY", "TWIN: compiled path on counterfactual employer wiring.", twin_items)
    write_batch(
        "compiler_probe_ONLY",
        "PROBE: sealed NL; report MID (1-hop) and ANSWER (final).",
        probe_items,
    )

    compile_ok = compile_n = 0
    for person in list(lexicon)[:20]:
        for tmpl in DEFAULT_TEMPLATES:
            compile_n += 1
            if compiler.compile(tmpl.format(person=person.replace("_", " "))).ok:
                compile_ok += 1

    harness = {
        "stack": "NL→PathCompiler→sealed PATH_QUERY→LLM execute",
        "n_cases": len(cases),
        "n_per_cond": 12,
        "compiler_selftest": f"{compile_ok}/{compile_n}",
        "rev": sealer.rev,
        "cases": cases,
    }
    (RESULTS / "compiler_stack_harness.json").write_text(json.dumps(harness, indent=2))
    print(json.dumps({"cases": len(cases), "compiler_selftest": f"{compile_ok}/{compile_n}"}, indent=2))


if __name__ == "__main__":
    main()
