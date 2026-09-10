#!/usr/bin/env python3
"""Middle layer: app English → LLM fully sealed Q + vault.

Paired isolation, per-item HMAC, real Wikidata names (spaces in the app Q).

  NOBIND  — HMAC the English question as-is (David / Schaeffer split).
            Start σ(David_Schaeffer) never lands in Q. No PROG.
            This is the start∉V(G) floor with a sealed question.

  LAYER   — layer binds the spaced name to the graph atom, HMAC the rest of Q
            (protect START), HMAC JSON keys+values, attach JOIN over sealed keys.
            LLM never sees plaintext names or English question words.

Not confidentiality (layer holds the key). Not unique-path G-Rev1 (PROG on LAYER).
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
from wilson_cis import wilson
from grev1_fullq_prog import seal_question, nest, country_of, KEYS, ATOM

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "seal_layer"
SEED = 20260818
N = 6
ENGLISH_Q = re.compile(r"\b(What|country|the|of|is|HQ|David|Bob)\b")


def pack(arm: str, cid: str, header: str, q: str, extra: str, ctx: str) -> str:
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. Do not open other files.",
            f"Format: ANSWER_SEALED[{cid}]: <seal_or_UNKNOWN>",
            "If more than one reading is possible, output UNKNOWN.",
            "",
            header,
            "",
            f"##### ID {cid} #####",
            "QUESTION (token-HMAC'd):",
            q,
            "",
            extra,
            "CONTEXT:",
            ctx,
            "",
        ]
    )


def leak_check(prompt: str, *names: str) -> bool:
    return any(n and n in prompt for n in names)


def build():
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    pool = [r for r in graph.records if r not in recs]

    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    cases = []
    for i, row in enumerate(recs):
        person, company, hq = row["person"], row["company"], row["hq"]
        country = country_of(hq)
        display = person.replace("_", " ")
        app_q = f"What is the country of {display}?"
        others = rng.sample(pool, 2)
        sealer = EntitySeal(rng.randbytes(16))
        k = {name: sealer.atom(name) for name in KEYS}
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
        ctx = json.dumps({k["employees"]: employees, k["orgs"]: orgs}, indent=2)

        nobind_q = sealer.text(app_q)
        layer_q = seal_question(f"What is the country of {pS}?", sealer, {pS})
        prog = (
            f"JOIN_QUERY\nSTART {pS}\n"
            f"In array {k['employees']}, match {k['id']} = START, take {k['employer']}.\n"
            f"In array {k['orgs']}, match {k['id']} = that employer, take {k['hq']}.{k['country']}.\n"
            f"Return that atom."
        )

        for arm, q, extra, header in (
            (
                "NOBIND",
                nobind_q,
                "",
                "ARM NOBIND: question HMAC'd as typed (spaced name splits). No PROG. No legend.",
            ),
            (
                "LAYER",
                layer_q,
                prog + "\n",
                "ARM LAYER: layer bound the name to START, HMAC'd the question, attached JOIN. No plaintext names.",
            ),
        ):
            cid = f"LAYER_{arm}_{i}"
            body = pack(arm, cid, header, q, extra, ctx)
            names = (person, display, company, hq, country, *[d["person"].replace("_", " ") for d in others])
            leaked = leak_check(body, *names)
            english_q = bool(ENGLISH_Q.search(q))
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            cases.append(
                {
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "gold": nS,
                    "trap": hS,
                    "start": pS,
                    "start_in_q": pS in q,
                    "english_in_q": english_q,
                    "plaintext_in_prompt": leaked,
                    "country_key_in_q": k["country"] in q,
                    "path": str(path),
                    "iso": True,
                    "per_item_key": True,
                    "app_q": app_q,
                    "plain_country": country,
                }
            )

    h = {
        "n": N,
        "suite": "seal_layer",
        "seed": SEED,
        "nonclaim": (
            "LAYER holds the key and the JOIN. LLM sees sealed Q+JSON. "
            "Not confidentiality. LAYER is product restore, not unique-path G-Rev1."
        ),
        "cases": cases,
    }
    out = RESULTS / "seal_layer_harness.json"
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False))
    nobind = [c for c in cases if c["arm"] == "NOBIND"]
    layer = [c for c in cases if c["arm"] == "LAYER"]
    print(
        json.dumps(
            {
                "n": N,
                "nobind_start_in_q": sum(c["start_in_q"] for c in nobind),
                "layer_start_in_q": sum(c["start_in_q"] for c in layer),
                "english_in_q": sum(c["english_in_q"] for c in cases),
                "leaks": sum(c["plaintext_in_prompt"] for c in cases),
                "nobind_country_key_in_q": sum(c["country_key_in_q"] for c in nobind),
                "sample_app": nobind[0]["app_q"],
                "sample_nobind_q": Path(nobind[0]["path"]).read_text().split("QUESTION (token-HMAC'd):")[1].split("CONTEXT:")[0].strip(),
                "out": str(out),
            },
            indent=2,
        )
    )


def score(model: str):
    H = json.loads((RESULTS / "seal_layer_harness.json").read_text())
    SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
    preds = {}
    d = RESULTS / f"seal_layer_replies_{model}"
    if d.exists():
        for p in d.rglob("*.txt"):
            text = p.read_text()
            tagged = list(SEAL.finditer(text))
            for m in tagged:
                preds[m.group(1)] = m.group(2).strip()
            if not tagged:
                mm = re.search(r"LAYER_(?:NOBIND|LAYER)_\d+", text)
                if mm and re.search(r"\bUNKNOWN\b", text, re.I):
                    preds[mm.group(0)] = "UNKNOWN"
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
        want_gold = c["arm"] == "LAYER"
        rows.append(
            {
                **{k: v for k, v in c.items() if k != "path"},
                "pred": pred,
                "kind": kind,
                "ok": (kind == "gold") if want_gold else (kind != "gold"),
            }
        )

    def arm_sum(arm: str):
        rs = [r for r in rows if r["arm"] == arm]
        n = len(rs)
        gold = sum(1 for r in rs if r["kind"] == "gold")
        return {
            "score": f"{gold}/{n}",
            "wilson": wilson(gold, n),
            "gold": gold,
            "unknown": sum(1 for r in rs if r["kind"] == "unknown"),
            "trap": sum(1 for r in rs if r["kind"] == "trap"),
            "missing": sum(1 for r in rs if r["kind"] == "missing"),
            "other": sum(1 for r in rs if r["kind"] == "other"),
        }

    summary = {"NOBIND": arm_sum("NOBIND"), "LAYER": arm_sum("LAYER")}
    path = RESULTS / f"seal_layer_{model}.json"
    path.write_text(
        json.dumps(
            {"model": model, "n": H["n"], "summary": summary, "nonclaim": H["nonclaim"], "rows": rows},
            indent=2,
        )
    )
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else "gpt56")
    else:
        build()
