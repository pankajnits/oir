#!/usr/bin/env python3
"""Hard cell: select country vs city on sealed JSON with no JOIN.

Question: does token equality between sealed q and sealed keys let the model
select the field (OIR-style), or only English/JOIN?

Arms (same 6 Wikidata people, city trap):
  ISO_SILENT  — same σ on Q words and JSON keys; no English; no JOIN
  ISO_RULE    — same σ + English equality rule; does not name country/city
  NS_SILENT   — JSONKEY: namespace so Q-word ≠ key (match impossible)
  ENG_SEALKEY — English Q; namespaced sealed keys (no iso match)
  ENG_ENGKEY  — English Q; English keys; sealed values (ARoG-like JSON)

Not confidentiality. Isolation, per-item HMAC. Seed 20260828.
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
from grev1_fullq_prog import KEYS, country_of, nest, seal_question
from seal_layer_legend import leak_check, pack, walk_json

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "opaque_iso_json"
SEED = 20260828
N = 6


def _suite_paths(n: int) -> tuple[Path, Path]:
    if n == N:
        return RUNS, RESULTS / "opaque_iso_json_harness.json"
    return ROOT / "runs" / f"opaque_iso_json_n{n}", RESULTS / f"opaque_iso_json_n{n}_harness.json"
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ATOM = re.compile(r"E[0-9a-f]{12}", re.I)

ISO_RULE = """
PROTOCOL (English; do not decrypt):
- QUESTION and CONTEXT use the same encoding.
- Identical tokens are the same entity or the same field (equality, not English).
- START is a QUESTION token that also appears as an id value in CONTEXT.
- The asked field is a QUESTION token that also appears as a JSON key.
- Walk CONTEXT by token equality. Return one sealed value.
- If more than one reading is possible, UNKNOWN.
No JOIN is given. Field names are not listed in English.
""".strip()


def q_tokens(q: str) -> set[str]:
    return set(ATOM.findall(q))


def build(n: int = N) -> dict:
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, n)
    pool = [r for r in graph.records if r not in recs]
    runs, out = _suite_paths(n)
    if runs.exists():
        for p in runs.rglob("prompt.txt"):
            p.unlink()

    arms = {
        a: {"ids": [], "item_paths": [], "sealed_answer": True}
        for a in ("ISO_SILENT", "ISO_RULE", "NS_SILENT", "ENG_SEALKEY", "ENG_ENGKEY")
    }
    cases = []

    for i, row in enumerate(recs):
        person, company, hq = row["person"], row["company"], row["hq"]
        country = country_of(hq)
        display = person.replace("_", " ")
        app_q = f"What is the country of {display}?"
        others = rng.sample(pool, 2)
        sealer = EntitySeal(rng.randbytes(16))
        k_iso = {name: sealer.atom(name) for name in KEYS}
        k_ns = {name: sealer.atom(f"JSONKEY:{name}") for name in KEYS}
        pS, cS, hS, nS = (sealer.atom(x) for x in (person, company, hq, country))

        def blob(k):
            employees = [{k["id"]: pS, k["employer"]: cS}]
            orgs = [{k["id"]: cS, k["hq"]: nest(k["city"], k["country"], hS, nS, rng)}]
            for d in others:
                dc = country_of(d["hq"])
                employees.append(
                    {k["id"]: sealer.atom(d["person"]), k["employer"]: sealer.atom(d["company"])}
                )
                orgs.append(
                    {
                        k["id"]: sealer.atom(d["company"]),
                        k["hq"]: nest(
                            k["city"],
                            k["country"],
                            sealer.atom(d["hq"]),
                            sealer.atom(dc),
                            rng,
                        ),
                    }
                )
            rng.shuffle(employees)
            rng.shuffle(orgs)
            ctx = json.dumps({k["employees"]: employees, k["orgs"]: orgs}, indent=2)
            assert walk_json(employees, orgs, k, pS) == nS
            return employees, orgs, ctx

        emp_iso, org_iso, ctx_iso = blob(k_iso)
        _, _, ctx_ns = blob(k_ns)
        eng_keys = {name: name for name in KEYS}
        _, _, ctx_eng = blob(eng_keys)

        q_iso = seal_question(f"What is the country of {pS}?", sealer, {pS})
        q_eng = f"What is the country of {pS}?"
        field_in_q = k_iso["country"] in q_tokens(q_iso)
        field_in_ns = k_ns["country"] in q_tokens(q_iso)
        assert field_in_q, "iso: sealed 'country' in Q must equal JSON key"
        assert not field_in_ns, "namespace must break Q-key equality"
        names = (person, display, company, hq, country, *[d["person"].replace("_", " ") for d in others])

        specs = [
            (
                "ISO_SILENT",
                q_iso,
                "",
                "ARM ISO_SILENT: same σ on Q and keys. No English. No JOIN. Select country vs city by token equality.",
                ctx_iso,
            ),
            (
                "ISO_RULE",
                q_iso,
                ISO_RULE + "\n",
                "ARM ISO_RULE: same σ + English equality rule. Does not name country. No JOIN.",
                ctx_iso,
            ),
            (
                "NS_SILENT",
                q_iso,
                "",
                "ARM NS_SILENT: Q sealed; keys namespaced JSONKEY:. Match impossible. No JOIN.",
                ctx_ns,
            ),
            (
                "ENG_SEALKEY",
                q_eng,
                "",
                "ARM ENG_SEALKEY: English Q (word country); namespaced sealed keys. No JOIN.",
                ctx_ns,
            ),
            (
                "ENG_ENGKEY",
                q_eng,
                "",
                "ARM ENG_ENGKEY: English Q; English keys; sealed values. No JOIN.",
                ctx_eng,
            ),
        ]
        for arm, q, extra, header, ctx in specs:
            cid = f"OIRJ_{arm}_{i}"
            body = pack(cid, header, q, extra, ctx)
            leaked = leak_check(body, *names)
            if arm != "ENG_ENGKEY":
                assert not leaked, (arm, i)
            path = runs / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            rec = {
                "arm": arm,
                "i": i,
                "id": cid,
                "gold": nS,
                "trap": hS,
                "start": pS,
                "field_in_q_iso": field_in_q,
                "field_in_q_ns": field_in_ns,
                "plaintext_in_prompt": leaked,
                "path": repo_rel(path),
                "app_q": app_q,
                "iso": True,
            }
            cases.append(rec)
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

    h = {
        "n": n,
        "suite": "opaque_iso_json",
        "seed": SEED,
        "nonclaim": (
            "ISO tests field selection by Q-key token equality, not JOIN. "
            "Guo/Fang cipher papers are sentence ciphers, not this. "
            "PrivGemo ranks retrieved paths and answers locally. Not confidentiality."
        ),
        "arms": arms,
        "cases": cases,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False))
    print(json.dumps({"n": n, "out": str(out), "iso_field_in_q": True}, indent=2))
    return h


def score(model: str, harness_name: str = "opaque_iso_json_harness.json") -> None:
    H = json.loads((RESULTS / harness_name).read_text())
    preds = {}
    d = RESULTS / f"{Path(harness_name).stem}_replies_{model}"
    if d.exists():
        for p in d.rglob("*.txt"):
            text = p.read_text()
            for m in SEAL.finditer(text):
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
            "wilson": wilson(gold, n) if n and missing < n else None,
            "gold": gold,
            "unknown": sum(1 for r in rs if r["kind"] == "unknown"),
            "trap": sum(1 for r in rs if r["kind"] == "trap"),
            "missing": missing,
            "other": sum(1 for r in rs if r["kind"] == "other"),
        }

    summary = {arm: arm_sum(arm) for arm in H["arms"]}
    path = RESULTS / f"{Path(harness_name).stem}_{model}.json"
    path.write_text(json.dumps({"model": model, "n": H["n"], "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else "gpt56", sys.argv[3] if len(sys.argv) > 3 else "opaque_iso_json_harness.json")
    else:
        build(int(sys.argv[1]) if len(sys.argv) > 1 else N)
