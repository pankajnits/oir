#!/usr/bin/env python3
"""Scout: non-leaking hints on sealed two-path failures.

Does not name gold, director/writer, or which sealed edge is correct.
Not a paper lock. Isolation. OpenAI only. n=8 (4 WikiMovies Cond B + 4 both-opaque).
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
LEAK = ("directed", "starred", "written", "writer", "director", "headquartered", "works_at")

HINTS = {
    "token_align": """
HINTS (English; do not decrypt; do not use world knowledge; the answer name is not given):
- Identical strings are the same object or the same edge label.
- The bracketed or already-opaque start in QUESTION is the walk origin.
- A relation is usable only if that exact token also appears in QUESTION.
- Walk CONTEXT by token equality. If no QUESTION token equals an edge label,
  or two 2-hops remain, answer UNKNOWN.
No JOIN. No legend. Do not name which English relation is intended.
""".strip(),
    "cot_enum": """
HINTS (English; do not decrypt; do not use world knowledge; the answer name is not given):
- List every 2-hop from the start that appears in CONTEXT.
- You may write brief working notes.
- If more than one 2-hop exists, answer only if QUESTION tokens uniquely pick
  one walk via exact string match to an edge label. Otherwise UNKNOWN.
- Do not choose by fame, movies you know, or companies you know.
No JOIN. No legend.
""".strip(),
    "no_guess": """
HINTS (English; the answer name is not given):
- Use only this file. Do not use prior knowledge.
- If CONTEXT has two complete 2-hops from the start, and QUESTION does not
  share any exact token with those edge labels, you must answer UNKNOWN.
- Do not pick a tail at random.
No JOIN. No legend.
""".strip(),
}

OUT = ROOT / "results" / "hint_scout_fail8.json"
REPLY = ROOT / "results" / "hint_scout_fail8_replies"
ITEMS = [
    ("wiki_b", "results/metaqa_2x2_people_n100_qhash_iso_harness.json", "OPAQUE_AMBIG", False, [0, 1, 2, 3]),
    ("oo", "results/entity_rel_2x2_iso_harness.json", "OO_AMBIG", True, [0, 1, 2, 3]),
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


def q_rel_overlap(prompt: str) -> int:
    q = prompt.split("QUESTION:", 1)[-1].split("CONTEXT:", 1)[0]
    ctx = prompt.split("CONTEXT:", 1)[-1]
    rels = []
    for ln in ctx.splitlines():
        parts = [p.strip() for p in ln.split("|")]
        if len(parts) == 3:
            rels.append(parts[1])
    qtok = {t.lower() for t in ATOM.findall(q)}
    rtok = {t.lower() for t in rels if ATOM.match(t)}
    return len(qtok & rtok)


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
    low = hint.lower()
    for w in LEAK:
        if w in low:
            raise SystemExit(f"hint leak: {w}")
    marker = "##### ID "
    if marker not in prompt:
        raise SystemExit("missing ID marker")
    return prompt.replace(marker, hint + "\n\n" + marker, 1)


def kind(pred: str, gold: str, decoy: str) -> str:
    p, g, d = pred.strip(), gold.strip(), decoy.strip()
    if p.upper() == "UNKNOWN":
        return "unknown"
    if p == g or p.replace("_", " ") == g.replace("_", " "):
        return "gold"
    if p == d or p.replace("_", " ") == d.replace("_", " "):
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
    for suite, harness_rel, arm, sealed, idxs in ITEMS:
        h = json.loads((ROOT / harness_rel).read_text())
        cases = {c["i"]: c for c in h["cases"]}
        paths = h["arms"][arm]["item_paths"]
        ids = h["arms"][arm]["ids"]
        for i in idxs:
            prompt0 = repo_abs(paths[i]).read_text()
            case = cases[i]
            gold = case["gold"] if suite == "wiki_b" else case["golds"][arm]
            decoy = case["decoy_hq"] if suite == "wiki_b" else case["decoys"][arm]
            overlap = q_rel_overlap(prompt0)
            cid = ids[i]
            for hint_name, hint in HINTS.items():
                prompt = inject(prompt0, hint)
                t0 = time.time()
                try:
                    raw = complete(client, model, prompt)
                    err = None
                except Exception as e:
                    raw, err = f"ERROR: {e}", str(e)
                pred = "UNKNOWN" if err else parse(cid, raw, sealed=sealed)
                k = "error" if err else kind(pred, gold, decoy)
                rec = {
                    "suite": suite,
                    "arm": arm,
                    "i": i,
                    "id": cid,
                    "hint": hint_name,
                    "q_rel_token_overlap": overlap,
                    "pred": pred,
                    "gold": gold,
                    "decoy": decoy,
                    "kind": k,
                    "sec": round(time.time() - t0, 1),
                }
                rows.append(rec)
                outp = REPLY / f"{suite}_{arm}_{i}_{hint_name}.txt"
                outp.write_text(raw if err else f"{pred}\n# raw\n{raw[:4000]}\n")
                print(f"{suite} {i} {hint_name} {rec['sec']}s overlap={overlap} -> {k} {pred}", flush=True)

    summary: dict[str, dict[str, int]] = {}
    for r in rows:
        key = f"{r['suite']}:{r['hint']}"
        summary.setdefault(key, {"gold": 0, "decoy": 0, "unknown": 0, "other": 0, "error": 0, "n": 0})
        summary[key][r["kind"]] += 1
        summary[key]["n"] += 1
    payload = {
        "n_items": 8,
        "hints": list(HINTS),
        "model": model,
        "note": "Scout only. Hints never name gold or the intended English relation. Ident32 vague hints remain the n=32 lock.",
        "summary": summary,
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print("wrote", OUT)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
