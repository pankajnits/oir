#!/usr/bin/env python3
"""Run Ollama MUT on adv_induction_n32_iso isolation prompts."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs

RESULTS = ROOT / "results"
HARNESS = RESULTS / "adv_induction_n32_iso_harness.json"
ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def ollama_generate(model: str, prompt: str, timeout: int = 300) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 256},
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    text = (data.get("response") or "").strip()
    if not text:
        text = (data.get("thinking") or "").strip()
    return text


def main() -> None:
    argv = [a for a in sys.argv[1:] if a != "--force"]
    model = argv[0] if len(argv) > 0 else "qwen3.5:latest"
    tag = argv[1] if len(argv) > 1 else "qwen35"
    arms = argv[2:] or [
        "SAME_TRAP",
        "CROSS_TRAP",
        "SAME_BALANCED",
        "CROSS_BALANCED",
    ]
    h = json.loads(HARNESS.read_text())
    reply_root = RESULTS / f"adv_n32_iso_replies_{tag}"
    reply_root.mkdir(parents=True, exist_ok=True)
    for arm in arms:
        meta = h["arms"][arm]
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(meta["item_paths"]):
            out = out_dir / f"item_{i}.txt"
            force = "--force" in sys.argv
            if (
                not force
                and out.exists()
                and "ANSWER_SEALED" in out.read_text()
                and "UNKNOWN\n# raw\n\n" not in out.read_text()
                and "# raw\n\n" not in out.read_text()
            ):
                # keep non-empty prior answers
                prev = out.read_text()
                if ANS_RE.search(prev) and "ERROR:" not in prev:
                    print(f"skip {arm} {i}")
                    continue
            prompt = repo_abs(p).read_text()
            cid = meta["ids"][i]
            t0 = time.time()
            try:
                raw = ollama_generate(model, prompt)
            except Exception as e:
                raw = f"ERROR: {e}"
            m = list(ANS_RE.finditer(raw))
            if m:
                pred = m[-1].group(2)
                text = f"ANSWER_SEALED[{cid}]: {pred}\n# raw_tail\n{raw[-800:]}\n"
            else:
                text = f"ANSWER_SEALED[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"
            out.write_text(text)
            print(f"{arm} item_{i} {time.time()-t0:.1f}s -> {pred if m else 'UNKNOWN'}")
    print("done", tag, arms)


if __name__ == "__main__":
    main()
