#!/usr/bin/env python3
"""Run OpenAI MUT on adv_induction_n32_iso isolation prompts (free-form).

Requires OPENAI_API_KEY. Does not write the key to disk.

  python3 harness/run_openai_adv_n32_iso.py [model] [tag] [arm...]
  # default: gpt-5.6-sol gpt56 SAME_TRAP CROSS_TRAP SAME_BALANCED CROSS_BALANCED
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
from paths import repo_abs

RESULTS = ROOT / "results"
HARNESS = RESULTS / "adv_induction_n32_iso_harness.json"
ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)

DEFAULT_ARMS = [
    "SAME_TRAP",
    "CROSS_TRAP",
    "SAME_BALANCED",
    "CROSS_BALANCED",
]


def complete(client: OpenAI, model: str, prompt: str, *, retries: int = 5) -> str:
    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Newer GPT-5.x models reject temperature / prefer max_completion_tokens.
    if model.startswith(("gpt-5", "o3", "o4")):
        kwargs["max_completion_tokens"] = 512
    else:
        kwargs["temperature"] = 0
        kwargs["max_tokens"] = 256
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = client.chat.completions.create(**kwargs)
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            last = e
            wait = min(60.0, 1.5**attempt)
            print(f"  retry {attempt+1}/{retries} after {wait:.1f}s: {e}", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"OpenAI complete failed after {retries} retries: {last}")


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in the environment (do not commit it).")
    argv = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    model = argv[0] if len(argv) > 0 else "gpt-5.6-sol"
    tag = argv[1] if len(argv) > 1 else "gpt56"
    arms = argv[2:] or DEFAULT_ARMS

    client = OpenAI()
    h = json.loads(HARNESS.read_text())
    reply_root = RESULTS / f"adv_n32_iso_replies_{tag}"
    reply_root.mkdir(parents=True, exist_ok=True)

    for arm in arms:
        meta = h["arms"][arm]
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(meta["item_paths"]):
            out = out_dir / f"item_{i}.txt"
            if not force and out.exists():
                prev = out.read_text()
                if ANS_RE.search(prev) and "ERROR:" not in prev:
                    print(f"skip {arm} {i}")
                    continue
            prompt = repo_abs(p).read_text()
            cid = meta["ids"][i]
            t0 = time.time()
            pred = "UNKNOWN"
            try:
                raw = complete(client, model, prompt)
            except Exception as e:
                raw = f"ERROR: {e}"
            m = list(ANS_RE.finditer(raw))
            if m:
                pred = m[-1].group(2)
                text = f"ANSWER_SEALED[{cid}]: {pred}\n# raw_tail\n{raw[-800:]}\n"
            else:
                # Fallback: bare sealed atom or UNKNOWN in free text
                atom = re.search(r"\b(E[0-9a-f]{12})\b", raw, re.I)
                if atom and "ERROR:" not in raw:
                    pred = atom.group(1)
                    text = f"ANSWER_SEALED[{cid}]: {pred}\n# raw\n{raw[:2500]}\n"
                elif re.search(r"\bUNKNOWN\b", raw, re.I) and "ERROR:" not in raw:
                    text = f"ANSWER_SEALED[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"
                else:
                    text = f"ANSWER_SEALED[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"
            out.write_text(text)
            print(f"{arm} item_{i} {time.time()-t0:.1f}s -> {pred}", flush=True)
    print("done", model, tag, arms)


if __name__ == "__main__":
    main()
