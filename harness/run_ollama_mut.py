#!/usr/bin/env python3
"""Scripted Ollama MUT (temp=0). One-quiz files. Isolation by construction.

Usage:
  python3 harness/run_ollama_mut.py qwen3.5:latest wiki_cf_plain_n200
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANS = re.compile(r"ANSWER_(?:PLAIN|SEALED)\[([^\]]+)\]:\s*(.+)$", re.I | re.M)


def ollama_generate(model: str, prompt: str, timeout: int = 180) -> str:
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


def suite_wiki_cf_plain_n200():
    h = json.loads((ROOT / "results" / "wiki_cf_n200_harness.json").read_text())
    iso = Path(h["iso_dir"])
    return sorted(iso.glob("*.txt")), "ANSWER_PLAIN"


def suite_spider_sql_n32():
    d = ROOT / "runs" / "spider_sql_n32" / "iso"
    return sorted(d.glob("*.txt")), "SQL"


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:latest"
    suite = sys.argv[2] if len(sys.argv) > 2 else "wiki_cf_plain_n200"
    if suite == "wiki_cf_plain_n200":
        files, _ = suite_wiki_cf_plain_n200()
        out = ROOT / "results" / "wiki_cf_n200_replies_qwen35"
    elif suite == "spider_sql_n32":
        files, _ = suite_spider_sql_n32()
        out = ROOT / "results" / "spider_sql_n32_replies_qwen35"
    else:
        raise SystemExit(suite)
    out.mkdir(parents=True, exist_ok=True)
    tag = model.replace(":", "_").replace("/", "_")
    log = []
    for i, p in enumerate(files):
        dest = out / p.name
        if dest.exists() and "MISSING" not in dest.read_text() and "ERROR" not in dest.read_text():
            continue
        t0 = time.time()
        try:
            raw = ollama_generate(model, p.read_text())
        except Exception as e:
            raw = f"ERROR: {e}"
        dest.write_text(raw)
        ms = list(ANS.finditer(raw))
        hit = ms[-1].group(0) if ms else "NO_PARSE"
        rec = {"i": i, "file": p.name, "sec": round(time.time() - t0, 2), "hit": hit[:80]}
        log.append(rec)
        print(json.dumps(rec), flush=True)
    (out / f"_log_{tag}.json").write_text(json.dumps(log, indent=2))
    print("done", model, suite, "n", len(files), "out", out)


if __name__ == "__main__":
    main()
