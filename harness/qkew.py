#!/usr/bin/env python3
"""Query-Key Equality Walker (QKEW).

Induce a nested-JSON join from token equality alone:
  START = the unique question atom that appears as a JSON *value*
  ATTR  = the unique question atom that appears as a JSON *key*
  Then chase ID-equalities (a value of one object appears in another) and
  read ATTR (possibly nested). If ATTR is missing or not unique, UNKNOWN.

No gold PATH, no English field names, no frozen HMAC lexicon.
Per-example keys work because the rule is equality, not a codebook.

This is an executor (SealRouter-class), not ``the LLM reasoned.''
It *characterizes* well-posed G-Rev1-Q: the query must name the sink as an
opaque atom that HMAC-matches a key. G-Rev1-NONE (Q=START only) is
underspecified: no ATTR → UNKNOWN.

Not G-Rev1-NONE. Not confidentiality.
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
from oir import EntitySeal  # noqa: E402
from oir.adapters import load_ceo_hq_graph  # noqa: E402
from wilson_cis import wilson  # noqa: E402

RESULTS = ROOT / "results"
ATOM = re.compile(r"\bE[0-9a-fA-F]{6,}\b")
COUNTRIES = ["USA", "France", "Japan", "Germany", "India", "Brazil", "Canada", "UK"]
KEYS = ("employees", "orgs", "id", "employer", "hq", "city", "country")


def atoms(text: str) -> list[str]:
    return list(dict.fromkeys(ATOM.findall(text)))


def collect_dicts(x, out: list):
    if isinstance(x, dict):
        out.append(x)
        for v in x.values():
            collect_dicts(v, out)
    elif isinstance(x, list):
        for v in x:
            collect_dicts(v, out)


def direct_atom_values(d: dict) -> list[str]:
    """Join keys only: string values on this object, not nested leaves."""
    return [v for v in d.values() if isinstance(v, str) and ATOM.fullmatch(v)]


def lookup_attr(d: dict, attr: str) -> list[str]:
    found = []
    if attr in d and isinstance(d[attr], str) and ATOM.fullmatch(d[attr]):
        found.append(d[attr])
    for v in d.values():
        if isinstance(v, dict):
            found.extend(lookup_attr(v, attr))
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, dict):
                    found.extend(lookup_attr(x, attr))
    return found


def qkew(question: str, ctx) -> str:
    if isinstance(ctx, str):
        ctx = json.loads(ctx)
    q_atoms = atoms(question)
    dicts: list[dict] = []
    collect_dicts(ctx, dicts)
    keys, vals = set(), set()
    for d in dicts:
        keys.update(d.keys())
        vals.update(direct_atom_values(d))
    attrs = [a for a in q_atoms if a in keys]
    starts = [a for a in q_atoms if a in vals and a not in keys]
    if len(attrs) != 1 or len(starts) != 1:
        return "UNKNOWN"
    attr, start = attrs[0], starts[0]
    by_val: dict[str, list[int]] = defaultdict(list)
    for i, d in enumerate(dicts):
        for v in direct_atom_values(d):
            by_val[v].append(i)
    seen = set()
    answers = []
    q = deque(i for i, d in enumerate(dicts) if start in direct_atom_values(d))
    while q:
        i = q.popleft()
        if i in seen:
            continue
        seen.add(i)
        answers.extend(lookup_attr(dicts[i], attr))
        for v in direct_atom_values(dicts[i]):
            for j in by_val.get(v, []):
                if j not in seen:
                    q.append(j)
    uniq = list(dict.fromkeys(answers))
    if len(uniq) == 1:
        return uniq[0]
    return "UNKNOWN"


def parse_prompt(text: str) -> tuple[str, str]:
    m = re.search(r"QUESTION:\s*(.*?)\s*CONTEXT:\s*", text, re.S)
    if not m:
        raise ValueError("no QUESTION/CONTEXT")
    rest = text[m.end() :]
    return m.group(1).strip(), rest.strip()


def country_of(hq: str) -> str:
    return COUNTRIES[sum(map(ord, hq)) % len(COUNTRIES)]


def nest(city_k, country_k, city_v, country_v, rng):
    items = list({city_k: city_v, country_k: country_v}.items())
    rng.shuffle(items)
    return dict(items)


def make_vault(sealer: EntitySeal, row, others, rng):
    k = {name: sealer.atom(name) for name in KEYS}
    person, company, hq = row["person"], row["company"], row["hq"]
    country = country_of(hq)
    pS, cS, hS, nS = (sealer.atom(x) for x in (person, company, hq, country))
    employees = [{k["id"]: pS, k["employer"]: cS}]
    orgs = [{k["id"]: cS, k["hq"]: nest(k["city"], k["country"], hS, nS, rng)}]
    for d in others:
        dc = country_of(d["hq"])
        employees.append({k["id"]: sealer.atom(d["person"]), k["employer"]: sealer.atom(d["company"])})
        orgs.append(
            {
                k["id"]: sealer.atom(d["company"]),
                k["hq"]: nest(k["city"], k["country"], sealer.atom(d["hq"]), sealer.atom(dc), rng),
            }
        )
    rng.shuffle(employees)
    rng.shuffle(orgs)
    ctx = {k["employees"]: employees, k["orgs"]: orgs}
    return ctx, pS, nS, hS, k["country"]


def score_locked_prompts():
    H = json.loads((RESULTS / "grev1_noprog_harness.json").read_text())
    rows = []
    by_arm: dict[str, list] = {}
    for c in H["cases"]:
        q, ctx = parse_prompt(Path(c["path"]).read_text())
        pred = qkew(q, ctx)
        if pred == c["gold"]:
            kind = "gold"
        elif pred == "UNKNOWN":
            kind = "unknown"
        elif pred == c.get("trap"):
            kind = "trap"
        else:
            kind = "other"
        rec = {"arm": c["arm"], "id": c["id"], "pred": pred, "gold": c["gold"], "kind": kind, "ok": kind == "gold"}
        rows.append(rec)
        by_arm.setdefault(c["arm"], []).append(rec)
    summary = {}
    for arm, recs in by_arm.items():
        n = len(recs)
        k = sum(1 for r in recs if r["ok"])
        unk = sum(1 for r in recs if r["kind"] == "unknown")
        summary[arm] = {"score": f"{k}/{n}", "unknown": unk, "wilson": wilson(k, n)}
    return summary, rows


def score_novel_keys(n=200, seed=20260817):
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(seed)
    oks_q, oks_n, trap_q = [], [], []
    for i in range(n):
        key = rng.randbytes(16)
        sealer = EntitySeal(key)
        recs = rng.sample(graph.records, 3)
        row, others = recs[0], recs[1:]
        ctx, pS, nS, hS, k_country = make_vault(sealer, row, others, rng)
        q_qkey = f"What is {k_country} of {pS}?"
        q_none = f"Answer for {pS}. Return one atom."
        pq, pn = qkew(q_qkey, ctx), qkew(q_none, ctx)
        oks_q.append(pq == nS)
        trap_q.append(pq == hS)
        oks_n.append(pn == nS)
    return {
        "n": n,
        "QKEY_novel_hmac": {"score": f"{sum(oks_q)}/{n}", "trap": sum(trap_q), "wilson": wilson(sum(oks_q), n)},
        "NONE_novel_hmac": {
            "score": f"{sum(oks_n)}/{n}",
            "note": "should be 0 — no ATTR in Q",
            "wilson": wilson(sum(oks_n), n),
        },
    }


def main():
    locked, rows = score_locked_prompts()
    novel = score_novel_keys()
    out = {
        "executor": "QKEW",
        "nonclaim": "Symbolic equality-join inducer, not an LLM, not G-Rev1-NONE, not confidentiality. No gold PATH.",
        "locked_iso_n6": locked,
        "novel_hmac_n200": novel,
        "rows": rows,
    }
    path = RESULTS / "qkew.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps({"locked": locked, "novel": novel, "out": str(path)}, indent=2))


if __name__ == "__main__":
    main()
