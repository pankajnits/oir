#!/usr/bin/env python3
"""Run Ollama MUT on adv_induction item prompts (automated local pilot)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs

RESULTS = ROOT / "results"
HARNESS = RESULTS / "adv_induction_harness.json"
REPLIES = RESULTS / "adv_induction_replies"
ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def ollama_generate(model: str, prompt: str, timeout: int = 180) -> str:
    # Prefer HTTP API for non-interactive
    import urllib.request

    body = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    ).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    return data.get("response", "")


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:latest"
    arms = sys.argv[2:] or ["SAME_BALANCED", "CROSS_BALANCED", "SAME_TRAP", "CROSS_TRAP"]
    h = json.loads(HARNESS.read_text())
    REPLIES.mkdir(parents=True, exist_ok=True)
    for arm in arms:
        meta = h["arms"].get(arm)
        if not meta:
            print("skip missing arm", arm)
            continue
        out_dir = REPLIES / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(meta["item_paths"]):
            prompt = repo_abs(p).read_text()
            # Keep prompts short enough: already one-quiz files
            t0 = time.time()
            try:
                raw = ollama_generate(model, prompt)
            except Exception as e:
                raw = f"ERROR: {e}"
            # Prefer parsed answer; else keep raw
            m = list(ANS_RE.finditer(raw))
            text = raw if m else raw
            # If model didn't use tag, try last line token
            if not m:
                # attempt salvage: write UNKNOWN
                cid = meta["ids"][i]
                text = f"ANSWER_SEALED[{cid}]: UNKNOWN\n# raw\n{raw[:2000]}"
            else:
                # rewrite clean
                cid = meta["ids"][i]
                pred = m[-1].group(2)
                text = f"ANSWER_SEALED[{cid}]: {pred}\n# raw_tail\n{raw[-500:]}"
            (out_dir / f"item_{i}.txt").write_text(text)
            print(f"{arm} item_{i} {time.time()-t0:.1f}s -> {(out_dir / f'item_{i}.txt')}")
    print("done", model, arms)


if __name__ == "__main__":
    main()
