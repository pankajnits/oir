#!/usr/bin/env python3
"""Scout: isomorphic / encoding-space hints on sealed two-path failures.

Pushes the model to reason in the encoded symbol space and commit to a tail.
Does not name gold, director/writer, or which sealed edge is correct.
Unhashed arm uses Condition A English questions (verbs remain).
Not a paper lock.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs  # type: ignore

ATOM = re.compile(r"\bE[0-9a-f]{12}\b", re.I)
ANS_SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ANS_PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*([^\n]+)", re.I)

ISO_HASHED = """
SETUP (isomorphic encoding; do not decrypt; do not print a legend):
CONTEXT is a structure-preserving renaming of a knowledge graph. Opaque tokens
replaced original strings with a collision-free map. Token equality is identity.
The middle field of each CONTEXT line is a sealed relation. Reason inside that
encoded symbol space: treat the tokens as first-class symbols, walk from the
start already present in the QUESTION, and use graph structure plus the encoded
QUESTION to choose among routes.

TASK: two complete 2-hops exist from the start. Commit to the single most
appropriate tail under an isomorphic reading. Prefer a concrete answer over
UNKNOWN. Do not use a written JOIN plan (there is none). Do not invent tokens
that are not in CONTEXT.
""".strip()

ISO_UNHASHED = """
SETUP (isomorphic encoding; do not decrypt; do not print a legend):
CONTEXT is a structure-preserving renaming of a knowledge graph. Edge labels
(and sometimes nodes) are opaque tokens. Token equality is identity. The
QUESTION is English. Align that intent with the encoded graph: reason in a
mixed space — English query, encoded edges — without inverting the map.

TASK: two complete 2-hops exist from the start. Commit to the single most
appropriate tail given the English question and the encoded CONTEXT. Prefer a
concrete answer over UNKNOWN. Do not use a written JOIN plan (there is none).
Do not invent tokens that are not in CONTEXT.
""".strip()

OUT = ROOT / "results" / "hint_scout_iso_space.json"
REPLY = ROOT / "results" / "hint_scout_iso_space_replies"

# 6 WikiMovies Cond B failures, 4 Wikidata opaque-rel failures, 4 both-opaque failures
SPECS = [
    {
        "suite": "wiki_hashed",
        "harness": "results/metaqa_2x2_people_n100_qhash_iso_harness.json",
        "arm": "OPAQUE_AMBIG",
        "idxs": [0, 1, 2, 3, 4, 5],
        "sealed": False,
        "hint": ISO_HASHED,
        "prompt_from": "hashed",
    },
    {
        "suite": "wiki_unhashed",
        "harness": "results/metaqa_2x2_people_n100_iso_harness.json",
        "arm": "OPAQUE_AMBIG",
        "idxs": [0, 1, 2, 3, 4, 5],
        "sealed": False,
        "hint": ISO_UNHASHED,
        "prompt_from": "unhashed",
    },
    {
        "suite": "wd_unhashed_q",
        "harness": "results/factorial_2x2_iso_harness.json",
        "arm": "OPAQUE_AMBIG",
        "idxs": [0, 1, 3, 4],
        "sealed": False,
        "hint": ISO_UNHASHED,
        "prompt_from": "unhashed",
    },
    {
        "suite": "oo_hashed_graph",
        "harness": "results/entity_rel_2x2_iso_harness.json",
        "arm": "OO_AMBIG",
        "idxs": [0, 1, 2, 3],
        "sealed": True,
        "hint": ISO_UNHASHED,
        "prompt_from": "unhashed",
    },
]


def load_env() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if line.startswith("OPENAI_API_KEY=") and "=" in line:
            os.environ.setdefault("OPENAI_API_KEY", line.split("=", 1)[1].strip().strip("'\""))
            return


def parse(cid: str, raw: str, *, sealed: bool) -> str:
    rx = ANS_SEAL if sealed else ANS_PLAIN
    ms = list(rx.finditer(raw))
    if ms:
        return ms[-1].group(2).strip()
    if sealed:
        atom = re.search(r"\b(E[0-9a-f]{12})\b", raw, re.I)
        if atom and "ERROR:" not in raw:
            return atom.group(1)
    if re.search(r"\bUNKNOWN\b", raw, re.I) and "ERROR:" not in raw:
        return "UNKNOWN"
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.startswith("#")]
    if lines and "ERROR:" not in raw:
        return lines[-1].split()[-1].strip(".,;:")
    return "UNKNOWN"


def complete(client: OpenAI, model: str, prompt: str) -> str:
    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 1024,
    }
    last: Exception | None = None
    for attempt in range(5):
        try:
            r = client.chat.completions.create(**kwargs)
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            last = e
            time.sleep(min(60.0, 1.8**attempt))
    raise RuntimeError(last)


def inject(prompt: str, hint: str) -> str:
    marker = "##### ID "
    if marker not in prompt:
        raise SystemExit("missing ID marker")
    return prompt.replace(marker, hint + "\n\n" + marker, 1)


def gold_decoy(suite: str, case: dict, arm: str) -> tuple[str, str]:
    if suite == "oo_hashed_graph":
        return case["golds"][arm], case["decoys"][arm]
    if suite == "wd_unhashed_q":
        return case["gold"], case["decoy_hq"]
    return case["gold"], case["decoy_hq"]


def kind(pred: str, gold: str, decoy: str) -> str:
    def norm(s: str) -> str:
        return s.strip().replace("_", " ").lower()

    p, g, d = norm(pred), norm(gold), norm(decoy)
    if p == "unknown":
        return "unknown"
    if p == g:
        return "gold"
    if p == d:
        return "decoy"
    return "other"


def main() -> None:
    load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY")
    model = os.environ.get("OIR_MODEL", "gpt-5.6-sol")
    client = OpenAI()
    REPLY.mkdir(parents=True, exist_ok=True)
    rows = []
    for spec in SPECS:
        h = json.loads((ROOT / spec["harness"]).read_text())
        cases = {c["i"]: c for c in h["cases"]}
        paths = h["arms"][spec["arm"]]["item_paths"]
        ids = h["arms"][spec["arm"]]["ids"]
        sealed = spec["sealed"]
        for i in spec["idxs"]:
            prompt0 = repo_abs(paths[i]).read_text()
            prompt = inject(prompt0, spec["hint"])
            gold, decoy = gold_decoy(spec["suite"], cases[i], spec["arm"])
            cid = ids[i]
            t0 = time.time()
            try:
                raw = complete(client, model, prompt)
                err = None
            except Exception as e:
                raw, err = f"ERROR: {e}", str(e)
            pred = "UNKNOWN" if err else parse(cid, raw, sealed=sealed)
            k = "error" if err else kind(pred, gold, decoy)
            rec = {
                "suite": spec["suite"],
                "arm": spec["arm"],
                "i": i,
                "id": cid,
                "pred": pred,
                "gold": gold,
                "decoy": decoy,
                "kind": k,
                "sec": round(time.time() - t0, 1),
            }
            rows.append(rec)
            (REPLY / f"{spec['suite']}_{i}.txt").write_text(
                raw if err else f"{pred}\n# raw\n{raw[:5000]}\n"
            )
            print(
                f"{spec['suite']} {i} {rec['sec']}s -> {k} {pred}",
                flush=True,
            )

    summary: dict[str, dict[str, int]] = {}
    for r in rows:
        summary.setdefault(
            r["suite"], {"gold": 0, "decoy": 0, "unknown": 0, "other": 0, "error": 0, "n": 0}
        )
        summary[r["suite"]][r["kind"]] += 1
        summary[r["suite"]]["n"] += 1
    payload = {
        "model": model,
        "note": (
            "Scout only. Iso/encoding-space hints; no gold name; no which-edge legend. "
            "wiki_unhashed is Condition A English verbs (directed/starred). "
            "Locked Condition A without this hint on the same 6 items was 6/6."
        ),
        "summary": summary,
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print("wrote", OUT)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
