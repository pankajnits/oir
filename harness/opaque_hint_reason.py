#!/usr/bin/env python3
"""Sealed question + in-message hints only. No JOIN. No English field names.

ABSTRACT  — iso Q/keys; vague 'reason in this message' + token match; no START/field recipe
TWO_REL   — employer vs mentor both have a country; Q names employer+country via same σ;
            ISO_RULE recipe; trap = mentor country
TWO_ABS   — same two-route graph as TWO_REL but ABSTRACT hints only

Seed 20260829. Isolation n=6. Not confidentiality.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal
from oir.adapters import load_ceo_hq_graph
from wilson_cis import locked_score, wilson
from paths import repo_rel
from grev1_fullq_prog import country_of, seal_question
from seal_layer_legend import leak_check, pack

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "opaque_hint_reason"
SEED = 20260829
N = 6


def _suite_paths(n: int) -> tuple[Path, Path]:
    if n == N:
        return RUNS, RESULTS / "opaque_hint_reason_harness.json"
    return ROOT / "runs" / f"opaque_hint_reason_n{n}", RESULTS / f"opaque_hint_reason_n{n}_harness.json"
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ATOM = re.compile(r"E[0-9a-f]{12}", re.I)
KEYS = ("employees", "orgs", "id", "employer", "mentor", "country")

ABSTRACT = """
HINTS (English; do not decrypt; do not use world knowledge):
- Everything you need is in this message: the encoded QUESTION and CONTEXT.
- Reason only over those tokens. Identical tokens are the same object or field.
- Align the encoded question with CONTEXT until one sealed answer is forced.
- If it is not forced, UNKNOWN.
No JOIN. No legend. Field names are not given in English.
""".strip()

ISO_RULE = """
HINTS (English; do not decrypt; do not use world knowledge):
- Everything you need is in this message.
- Identical tokens are the same entity or field.
- START is a QUESTION token that also appears as an id value.
- Asked fields are QUESTION tokens that also appear as JSON keys.
- Walk CONTEXT by token equality. Return one sealed value or UNKNOWN.
No JOIN. Field names are not listed in English.
""".strip()


def build(n: int = N) -> dict:
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, n)
    pool = [r for r in graph.records if r not in recs]
    runs, outp = _suite_paths(n)
    if runs.exists():
        for p in runs.rglob("prompt.txt"):
            p.unlink()
    arms = {a: {"ids": [], "item_paths": [], "sealed_answer": True} for a in ("ABSTRACT", "TWO_REL")}
    cases = []

    for i, row in enumerate(recs):
        person, company, hq = row["person"], row["company"], row["hq"]
        decoy = rng.choice(pool)
        country = country_of(hq)
        trap_c = country_of(decoy["hq"])
        if trap_c == country:
            trap_c = "TRAPLAND"
        display = person.replace("_", " ")
        others = rng.sample([r for r in pool if r is not decoy], 1)
        sealer = EntitySeal(rng.randbytes(16))
        k = {name: sealer.atom(name) for name in KEYS}
        pS = sealer.atom(person)
        cS = sealer.atom(company)
        mS = sealer.atom(decoy["company"])
        nS = sealer.atom(country)
        tS = sealer.atom(trap_c)
        oS = sealer.atom(others[0]["person"])
        ocS = sealer.atom(others[0]["company"])
        onS = sealer.atom(country_of(others[0]["hq"]))

        employees = [
            {k["id"]: pS, k["employer"]: cS, k["mentor"]: mS},
            {k["id"]: oS, k["employer"]: ocS, k["mentor"]: cS},
        ]
        rng.shuffle(employees)
        orgs = [
            {k["id"]: cS, k["country"]: nS},
            {k["id"]: mS, k["country"]: tS},
            {k["id"]: ocS, k["country"]: onS},
        ]
        rng.shuffle(orgs)
        ctx = json.dumps({k["employees"]: employees, k["orgs"]: orgs}, indent=2)
        q = seal_question(f"What is the country of the employer of {pS}?", sealer, {pS})
        qtok = set(ATOM.findall(q))
        assert k["country"] in qtok and k["employer"] in qtok
        assert k["mentor"] not in qtok
        names = (person, display, company, decoy["person"].replace("_", " "), country, trap_c)

        for arm, extra, header in (
            (
                "ABSTRACT",
                ABSTRACT + "\n",
                "ARM ABSTRACT: two-route graph; sealed Q; vague in-message hints only. No JOIN.",
            ),
            (
                "TWO_REL",
                ISO_RULE + "\n",
                "ARM TWO_REL: same graph; sealed Q names employer; explicit equality recipe. No JOIN.",
            ),
        ):
            cid = f"OHR_{arm}_{i}"
            body = pack(cid, header, q, extra, ctx)
            assert not leak_check(body, *names), (arm, i)
            path = runs / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            rec = {
                "arm": arm,
                "i": i,
                "id": cid,
                "gold": nS,
                "trap": tS,
                "start": pS,
                "path": repo_rel(path),
                "app_q": f"What is the country of the employer of {display}?",
                "iso": True,
            }
            cases.append(rec)
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

    h = {
        "n": n,
        "suite": "opaque_hint_reason",
        "seed": SEED,
        "nonclaim": "Sealed Q + in-message hints. TWO_REL trap is mentor country. Not JOIN. Not confidentiality.",
        "arms": arms,
        "cases": cases,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(h, indent=2, ensure_ascii=False))
    print(json.dumps({"n": n, "out": str(outp)}, indent=2))
    return h


def score(model: str, harness_name: str = "opaque_hint_reason_harness.json") -> None:
    H = json.loads((RESULTS / harness_name).read_text())
    preds = {}
    d = RESULTS / f"{Path(harness_name).stem}_replies_{model}"
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
        rows.append({**{k: v for k, v in c.items() if k != "path"}, "pred": pred, "kind": kind})

    def arm_sum(arm: str):
        rs = [r for r in rows if r["arm"] == arm]
        n = len(rs)
        gold = sum(1 for r in rs if r["kind"] == "gold")
        missing = sum(1 for r in rs if r["kind"] == "missing")
        return {
            "score": locked_score(gold, n, missing=missing),
            "gold": gold,
            "unknown": sum(1 for r in rs if r["kind"] == "unknown"),
            "trap": sum(1 for r in rs if r["kind"] == "trap"),
            "other": sum(1 for r in rs if r["kind"] == "other"),
            "missing": missing,
        }

    summary = {a: arm_sum(a) for a in H["arms"]}
    path = RESULTS / f"{Path(harness_name).stem}_{model}.json"
    path.write_text(json.dumps({"model": model, "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else "gpt56", sys.argv[3] if len(sys.argv) > 3 else "opaque_hint_reason_harness.json")
    else:
        build(int(sys.argv[1]) if len(sys.argv) > 1 else N)
