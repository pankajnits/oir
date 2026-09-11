#!/usr/bin/env python3
"""OpenAI MUT on isolation harness JSON with ANSWER_PLAIN / ANSWER_SEALED.

  python3 harness/run_openai_iso_harness.py results/factorial_2x2_iso_harness.json gpt56 [arm...]
      [--force] [--retry-empty] [--model gpt-5.6-sol]
      [--max-completion-tokens 512] [--reasoning-effort medium]

Defaults reproduce the locked paper runner (512 completion tokens, reasoning
effort not sent, alias model id). Review fixes:

* empty completions are stored as NO_OUTPUT (not UNKNOWN) and are not final;
* a JSON sidecar per item keeps the full reply, finish_reason, usage, returned
  model id, response id, request settings and a UTC timestamp;
* --retry-empty re-queries locked files that were empty completions;
* --max-completion-tokens / --reasoning-effort make the budget explicit.
  Pin a dated snapshot with --model when rerunning for a paper cell.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs  # noqa: E402
from reply_parse import classify, is_final, parse  # noqa: E402

RESULTS = ROOT / "results"


def _dump(obj):
    if obj is None:
        return None
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return str(obj)


def complete(client, model: str, prompt: str, *, max_completion_tokens: int,
             reasoning_effort: str | None, retries: int = 6) -> tuple[str, dict]:
    kwargs: dict = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if model.startswith(("gpt-5", "o3", "o4")):
        kwargs["max_completion_tokens"] = max_completion_tokens
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
    else:
        kwargs["temperature"] = 0
        kwargs["max_tokens"] = 256
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = client.chat.completions.create(**kwargs)
            choice = r.choices[0]
            meta = {
                "request": {k: v for k, v in kwargs.items() if k != "messages"},
                "response_id": getattr(r, "id", None),
                "returned_model": getattr(r, "model", None),
                "created": getattr(r, "created", None),
                "finish_reason": getattr(choice, "finish_reason", None),
                "usage": _dump(getattr(r, "usage", None)),
                "attempts": attempt + 1,
            }
            return (choice.message.content or "").strip(), meta
        except Exception as e:  # network / rate limit
            last = e
            wait = min(90.0, 1.8**attempt)
            print(f"  retry {attempt + 1}/{retries} after {wait:.1f}s: {e}", flush=True)
            time.sleep(wait)
    raise RuntimeError(last)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("harness", nargs="?", default=str(RESULTS / "factorial_2x2_iso_harness.json"))
    ap.add_argument("tag", nargs="?", default="gpt56")
    ap.add_argument("arms", nargs="*")
    ap.add_argument("--force", action="store_true", help="re-query every item")
    ap.add_argument("--retry-empty", action="store_true",
                    help="re-query locked replies that were empty completions stored as UNKNOWN")
    ap.add_argument("--model", default=os.environ.get("OIR_MODEL", "gpt-5.6-sol"))
    ap.add_argument("--max-completion-tokens", type=int,
                    default=int(os.environ.get("OIR_MAX_COMPLETION_TOKENS", "512")))
    ap.add_argument("--reasoning-effort", default=os.environ.get("OIR_REASONING_EFFORT") or None)
    args = ap.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in the environment (do not commit it).")
    from openai import OpenAI

    harness_path = Path(args.harness)
    h = json.loads(harness_path.read_text())
    arms = args.arms or list(h["arms"])
    client = OpenAI()
    reply_root = RESULTS / f"{harness_path.stem}_replies_{args.tag}"
    reply_root.mkdir(parents=True, exist_ok=True)
    for arm in arms:
        meta = h["arms"][arm]
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        sealed = bool(meta.get("sealed_answer"))
        for i, p in enumerate(meta["item_paths"]):
            out = out_dir / f"item_{i}.txt"
            if not args.force and out.exists():
                prev = out.read_text()
                if is_final(prev) and not (args.retry_empty and classify(prev) == "legacy_empty"):
                    print(f"skip {arm} {i}", flush=True)
                    continue
            cid = meta["ids"][i]
            t0 = time.time()
            info: dict = {}
            try:
                raw, info = complete(client, args.model, repo_abs(p).read_text(),
                                     max_completion_tokens=args.max_completion_tokens,
                                     reasoning_effort=args.reasoning_effort)
            except Exception as e:
                raw = f"ERROR: {e}"
            pred, text = parse(cid, raw, sealed=sealed)
            if raw.startswith("ERROR:"):
                text = f"ERROR: {raw}\n"
            out.write_text(text)
            sidecar = {
                "id": cid, "arm": arm, "item": i, "prompt_path": p, "pred": pred,
                "raw": raw, "elapsed_s": round(time.time() - t0, 3),
                "utc": datetime.now(timezone.utc).isoformat(), **info,
            }
            out.with_suffix(".json").write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n")
            fr = info.get("finish_reason")
            print(f"{arm} item_{i} {time.time() - t0:.1f}s -> {pred} (finish={fr})", flush=True)
    print("done", args.model, args.tag, arms)


if __name__ == "__main__":
    main()
