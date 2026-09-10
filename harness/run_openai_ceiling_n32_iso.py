#!/usr/bin/env python3
"""OpenAI free-form MUT on isolation three-arm n=32. Requires OPENAI_API_KEY."""
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
HARNESS = RESULTS / "ceiling_three_arm_n32_iso_harness.json"
ANS_SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ANS_PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*([^\n]+)", re.I)


def complete(client: OpenAI, model: str, prompt: str, *, retries: int = 6) -> str:
    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
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
            wait = min(90.0, 1.8**attempt)
            print(f"  retry {attempt + 1}/{retries} after {wait:.1f}s: {e}", flush=True)
            time.sleep(wait)
    raise RuntimeError(last)


def parse(arm: str, cid: str, raw: str) -> tuple[str, str]:
    if arm == "PLAIN_PROG":
        ms = list(ANS_PLAIN.finditer(raw))
        if ms:
            pred = ms[-1].group(2).strip()
            return pred, f"ANSWER_PLAIN[{cid}]: {pred}\n# raw_tail\n{raw[-800:]}\n"
        return "UNKNOWN", f"ANSWER_PLAIN[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"
    ms = list(ANS_SEAL.finditer(raw))
    if ms:
        pred = ms[-1].group(2).strip()
        return pred, f"ANSWER_SEALED[{cid}]: {pred}\n# raw_tail\n{raw[-800:]}\n"
    atom = re.search(r"\b(E[0-9a-f]{12})\b", raw, re.I)
    if atom and "ERROR:" not in raw:
        pred = atom.group(1)
        return pred, f"ANSWER_SEALED[{cid}]: {pred}\n# raw\n{raw[:2500]}\n"
    if re.search(r"\bUNKNOWN\b", raw, re.I) and "ERROR:" not in raw:
        return "UNKNOWN", f"ANSWER_SEALED[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"
    return "UNKNOWN", f"ANSWER_SEALED[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in the environment (do not commit it).")
    argv = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    model = argv[0] if len(argv) > 0 else "gpt-5.6-sol"
    tag = argv[1] if len(argv) > 1 else "gpt56"
    arms = argv[2:] or ["PLAIN_PROG", "SEAL_PROG", "SEAL_NL"]
    client = OpenAI()
    h = json.loads(HARNESS.read_text())
    reply_root = RESULTS / f"ceiling_n32_iso_replies_{tag}"
    reply_root.mkdir(parents=True, exist_ok=True)
    for arm in arms:
        meta = h["arms"][arm]
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(meta["item_paths"]):
            out = out_dir / f"item_{i}.txt"
            if not force and out.exists():
                prev = out.read_text()
                if "ERROR:" not in prev and (ANS_SEAL.search(prev) or ANS_PLAIN.search(prev)):
                    print(f"skip {arm} {i}", flush=True)
                    continue
            cid = meta["ids"][i]
            t0 = time.time()
            try:
                raw = complete(client, model, repo_abs(p).read_text())
            except Exception as e:
                raw = f"ERROR: {e}"
            pred, text = parse(arm, cid, raw)
            if raw.startswith("ERROR:"):
                text = f"ERROR: {raw}\n"
            out.write_text(text)
            print(f"{arm} item_{i} {time.time() - t0:.1f}s -> {pred}", flush=True)
    print("done", model, tag, arms)


if __name__ == "__main__":
    main()
