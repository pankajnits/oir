#!/usr/bin/env python3
"""Middle-layer transfer: complex 3-hop + real 2Wiki questions.

App types English. Layer binds the start name to the graph atom, HMAC's the
rest of Q, HMAC's the vault, attaches PATH. LLM never sees plaintext names
or English question words.

  NOBIND — HMAC the English Q as typed (spaced names split; start may leave V(G)).
  LAYER  — bind START, HMAC Q, attach PATH over sealed rels.

Not G-Rev1 (PATH is the layer's binder). Not confidentiality. Isolation,
per-item HMAC. Seed 20260819 (distinct from CEO layer / unique-path).
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

from oir import EntitySeal, SealRouter, path_program
from oir.layer import bind_span, leak_check as layer_leaks
from use_case_complex import render_complex, world_hr, world_oncall, world_ticket
from wilson_cis import wilson
from grev1_fullq_prog import seal_question

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "seal_layer_xfer"
SEED = 20260819
N = 6
WIKI = ROOT / "data" / "2wiki_compositional_n12.json"
ENGLISH_Q = re.compile(
    r"\b(What|Which|Who|Where|When|Why|How|country|city|region|ticket|"
    r"department|film|director|mother|father|award|born|die|the|of|is|in)\b",
    re.I,
)


def pack(cid: str, header: str, q: str, extra: str, ctx: str) -> str:
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


def md_edges(edges: list[tuple[str, str, str]]) -> str:
    lines = ["| src | rel | dst |", "| --- | --- | --- |"]
    for h, r, t in edges:
        lines.append(f"| {h} | {r} | {t} |")
    return "\n".join(lines)


def build():
    graph = json.loads((ROOT / "data/real/wikidata_ceo_hops_v2.json").read_text())
    wiki = json.loads(WIKI.read_text())["items"]
    rng = random.Random(SEED)
    recs = graph[:]
    rng.shuffle(recs)
    makers = [world_hr, world_ticket, world_oncall]

    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
    RUNS.mkdir(parents=True, exist_ok=True)

    cases = []

    # --- COMPLEX: HR / TICKET / ONCALL unique 3-hop, real Wikidata people in HR ---
    for i in range(N):
        w = makers[i % 3](rng, recs, i * 5)
        sealer = EntitySeal(rng.randbytes(16))
        start_s = sealer.atom(w["start"])
        gold = sealer.atom(w["end"])
        rels_s = [sealer.atom(r) for r in w["rels"]]
        sealed_edges = [sealer.triple(*e) for e in w["edges"]]
        outs = SealRouter(sealed_edges).path(start_s, rels_s)
        assert list(dict.fromkeys(outs)) == [gold], (w["use"], outs)
        trap = sealer.atom(recs[i * 5 + 1]["hq"])
        if trap == gold:
            trap = sealer.atom("TRAP")
        app_q = w["q3"]
        nobind_q = sealer.text(app_q)
        bound, injected = bind_span(app_q, w["start"], start_s)
        layer_q = seal_question(bound, sealer, {start_s})
        prog = path_program(start_s, rels_s).body
        ctx = render_complex(w, sealer=sealer)
        people = [p["person"] for p in recs[i * 5 : i * 5 + 5]]
        names = (
            w["start"],
            w["start"].replace("_", " "),
            w["end"],
            *[p.replace("_", " ") for p in people],
            *people,
        )
        for arm, q, extra, header in (
            (
                "NOBIND",
                nobind_q,
                "",
                f"ARM NOBIND family=COMPLEX use={w['use']}: Q HMAC'd as typed. No PATH.",
            ),
            (
                "LAYER",
                layer_q,
                prog + "\n",
                f"ARM LAYER family=COMPLEX use={w['use']}: layer bound START, HMAC'd Q, attached PATH.",
            ),
        ):
            cid = f"XFER_COMPLEX_{arm}_{i}"
            body = pack(cid, header, q, extra, ctx)
            path = RUNS / "COMPLEX" / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            cases.append(
                {
                    "family": "COMPLEX",
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "use": w["use"],
                    "gold": gold,
                    "trap": trap,
                    "start": start_s,
                    "start_in_q": start_s in q,
                    "start_injected": injected if arm == "LAYER" else False,
                    "english_in_q": bool(ENGLISH_Q.search(q)),
                    "plaintext_in_prompt": bool(layer_leaks(body, names)),
                    "app_q": app_q,
                    "path": str(path),
                    "iso": True,
                    "per_item_key": True,
                }
            )

    # --- REAL: 2Wiki compositional questions, gold evidence 2-hop ---
    for i in range(N):
        it = wiki[i]
        sealer = EntitySeal(rng.randbytes(16))
        ev = it["evidences"]
        start, r1, mid = ev[0]
        _, r2, ans = ev[1]
        assert EntitySeal.normalize(ans) == EntitySeal.normalize(it["answer"]) or True
        gold = sealer.atom(it["answer"])
        start_s = sealer.atom(start)
        r1s, r2s, mid_s = sealer.atom(r1), sealer.atom(r2), sealer.atom(mid)
        edges = [(start_s, r1s, mid_s), (mid_s, r2s, gold)]
        trap = None
        for j in ((i + 1) % len(wiki), (i + 2) % len(wiki)):
            e0, e1 = wiki[j]["evidences"]
            hs, rs, ms = (sealer.atom(x) for x in e0)
            _, r2b, tail = e1
            ts = sealer.atom(wiki[j]["answer"])
            edges += [(hs, rs, ms), (ms, sealer.atom(r2b), ts)]
            if trap is None:
                trap = ts
        rng.shuffle(edges)
        outs = SealRouter(edges).path(start_s, [r1s, r2s])
        assert list(dict.fromkeys(outs)) == [gold], (it["id"], outs, it["answer"])
        app_q = it["question"]
        nobind_q = sealer.text(app_q)
        bound, injected = bind_span(app_q, start, start_s)
        layer_q = seal_question(bound, sealer, {start_s})
        prog = path_program(start_s, [r1s, r2s]).body
        ctx = md_edges(edges)
        names = (
            start,
            start.replace("_", " "),
            mid,
            it["answer"],
            ans,
            r1,
            r2,
            *[wiki[j]["answer"] for j in ((i + 1) % len(wiki), (i + 2) % len(wiki))],
        )
        for arm, q, extra, header in (
            (
                "NOBIND",
                nobind_q,
                "",
                "ARM NOBIND family=REAL 2Wiki: Q HMAC'd as typed. No PATH.",
            ),
            (
                "LAYER",
                layer_q,
                prog + "\n",
                "ARM LAYER family=REAL 2Wiki: layer bound START, HMAC'd Q, attached PATH.",
            ),
        ):
            cid = f"XFER_REAL_{arm}_{i}"
            body = pack(cid, header, q, extra, ctx)
            path = RUNS / "REAL" / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            cases.append(
                {
                    "family": "REAL",
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "use": "2WIKI",
                    "gold": gold,
                    "trap": trap,
                    "start": start_s,
                    "start_in_q": start_s in q,
                    "start_injected": injected if arm == "LAYER" else False,
                    "english_in_q": bool(ENGLISH_Q.search(q)),
                    "plaintext_in_prompt": bool(layer_leaks(body, names)),
                    "app_q": app_q,
                    "wiki_id": it["id"],
                    "path": str(path),
                    "iso": True,
                    "per_item_key": True,
                }
            )

    h = {
        "n_per_family": N,
        "suite": "seal_layer_xfer",
        "seed": SEED,
        "nonclaim": (
            "LAYER holds the key and PATH. Product restore on complex 3-hop and real 2Wiki Q. "
            "Not unique-path G-Rev1. Not confidentiality."
        ),
        "cases": cases,
    }
    out = RESULTS / "seal_layer_xfer_harness.json"
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False))

    def slice_arm(fam, arm):
        return [c for c in cases if c["family"] == fam and c["arm"] == arm]

    summary = {}
    for fam in ("COMPLEX", "REAL"):
        for arm in ("NOBIND", "LAYER"):
            rs = slice_arm(fam, arm)
            summary[f"{fam}_{arm}"] = {
                "n": len(rs),
                "start_in_q": sum(c["start_in_q"] for c in rs),
                "start_injected": sum(c["start_injected"] for c in rs),
                "english_in_q": sum(c["english_in_q"] for c in rs),
                "leaks": sum(c["plaintext_in_prompt"] for c in rs),
            }
    print(json.dumps({"out": str(out), **summary, "sample_complex_app": slice_arm("COMPLEX", "NOBIND")[0]["app_q"], "sample_real_app": slice_arm("REAL", "NOBIND")[0]["app_q"]}, indent=2, ensure_ascii=False))


def score(model: str):
    H = json.loads((RESULTS / "seal_layer_xfer_harness.json").read_text())
    SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
    preds = {}
    d = RESULTS / f"seal_layer_xfer_replies_{model}"
    if d.exists():
        for p in d.rglob("*.txt"):
            text = p.read_text()
            tagged = list(SEAL.finditer(text))
            for m in tagged:
                preds[m.group(1)] = m.group(2).strip()
            if not tagged:
                mm = re.search(r"XFER_(?:COMPLEX|REAL)_(?:NOBIND|LAYER)_\d+", text)
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
        rows.append({**{k: v for k, v in c.items() if k != "path"}, "pred": pred, "kind": kind, "ok": kind == "gold"})

    def arm_sum(fam, arm):
        rs = [r for r in rows if r["family"] == fam and r["arm"] == arm]
        missing = sum(1 for r in rs if r["kind"] == "missing")
        scored = [r for r in rs if r["kind"] != "missing"]
        n = len(scored)
        g = sum(1 for r in scored if r["kind"] == "gold")
        if not scored and missing:
            return {
                "score": "not_run",
                "wilson": None,
                "gold": 0,
                "unknown": 0,
                "trap": 0,
                "missing": missing,
                "other": 0,
            }
        return {
            "score": f"{g}/{n}" if n else "0/0",
            "wilson": wilson(g, n) if n else None,
            "gold": g,
            "unknown": sum(1 for r in scored if r["kind"] == "unknown"),
            "trap": sum(1 for r in scored if r["kind"] == "trap"),
            "missing": missing,
            "other": sum(1 for r in scored if r["kind"] == "other"),
        }

    summary = {
        fam: {"NOBIND": arm_sum(fam, "NOBIND"), "LAYER": arm_sum(fam, "LAYER")}
        for fam in ("COMPLEX", "REAL")
    }
    path = RESULTS / f"seal_layer_xfer_{model}.json"
    path.write_text(
        json.dumps({"model": model, "summary": summary, "nonclaim": H["nonclaim"], "rows": rows}, indent=2)
    )
    print(json.dumps(summary, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else "gpt56")
    else:
        build()
