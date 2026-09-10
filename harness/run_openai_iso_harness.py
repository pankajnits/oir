#!/usr/bin/env python3
"""OpenAI MUT on isolation harness JSON with ANSWER_PLAIN / ANSWER_SEALED.

  python3 harness/run_openai_iso_harness.py results/factorial_2x2_iso_harness.json gpt56 [arm...]
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


def parse(cid: str, raw: str, *, sealed: bool) -> tuple[str, str]:
    rx = ANS_SEAL if sealed else ANS_PLAIN
    prefix = "ANSWER_SEALED" if sealed else "ANSWER_PLAIN"
    ms = list(rx.finditer(raw))
    if ms:
        pred = ms[-1].group(2).strip()
        return pred, f"{prefix}[{cid}]: {pred}\n# raw_tail\n{raw[-800:]}\n"
    if sealed:
        atom = re.search(r"\b(E[0-9a-f]{12})\b", raw, re.I)
        if atom and "ERROR:" not in raw:
            pred = atom.group(1)
            return pred, f"{prefix}[{cid}]: {pred}\n# raw\n{raw[:2500]}\n"
    if re.search(r"\bUNKNOWN\b", raw, re.I) and "ERROR:" not in raw:
        return "UNKNOWN", f"{prefix}[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"
    # last non-empty line as fallback city
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.startswith("#")]
    if lines and "ERROR:" not in raw:
        pred = lines[-1].split()[-1].strip(".,;:")
        return pred, f"{prefix}[{cid}]: {pred}\n# raw\n{raw[:2500]}\n"
    return "UNKNOWN", f"{prefix}[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in the environment (do not commit it).")
    argv = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    harness_path = Path(argv[0]) if argv else RESULTS / "factorial_2x2_iso_harness.json"
    tag = argv[1] if len(argv) > 1 else "gpt56"
    model = os.environ.get("OIR_MODEL", "gpt-5.6-sol")
    h = json.loads(harness_path.read_text())
    arms = argv[2:] or list(h["arms"])
    client = OpenAI()
    reply_root = RESULTS / f"{harness_path.stem}_replies_{tag}"
    reply_root.mkdir(parents=True, exist_ok=True)
    for arm in arms:
        meta = h["arms"][arm]
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        sealed = bool(meta.get("sealed_answer"))
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
            pred, text = parse(cid, raw, sealed=sealed)
            if raw.startswith("ERROR:"):
                text = f"ERROR: {raw}\n"
            out.write_text(text)
            print(f"{arm} item_{i} {time.time() - t0:.1f}s -> {pred}", flush=True)
    print("done", model, tag, arms)


if __name__ == "__main__":
    main()
