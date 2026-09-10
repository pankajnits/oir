#!/usr/bin/env python3
"""Ollama MUT on a whole BATCH.txt (temp=0). Faster than 200 iso calls."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gen(model: str, prompt: str, timeout: int = 600) -> str:
    body = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0, "num_ctx": 16384}}
    ).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode()).get("response", "")


def main():
    model = sys.argv[1]
    src = Path(sys.argv[2])
    dest = Path(sys.argv[3])
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("prompt_chars", len(src.read_text()), flush=True)
    raw = gen(model, src.read_text())
    dest.write_text(raw)
    print("wrote", dest, "chars", len(raw))


if __name__ == "__main__":
    main()
