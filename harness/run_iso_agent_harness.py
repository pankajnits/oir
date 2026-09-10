#!/usr/bin/env python3
"""Isolation MUT (composer-2.5 / Grok) on isolation harness JSON.

No tools, empty cwd — the model cannot read gold JSON.
Skips existing reply files. Does not re-run OpenAI.

  AGENT_API_KEY=... python3 harness/run_iso_agent_harness.py \\
      results/factorial_2x2_iso_harness.json composer25 composer-2.5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs

RESULTS = ROOT / "results"
ANS_SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ANS_PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*([^\n]+)", re.I)


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
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.startswith("#")]
    if lines and "ERROR:" not in raw:
        pred = lines[-1].split()[-1].strip(".,;:")
        return pred, f"{prefix}[{cid}]: {pred}\n# raw\n{raw[:2500]}\n"
    return "UNKNOWN", f"{prefix}[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"


async def one(
    *,
    client,
    model: str,
    api_key: str,
    cwd: str,
    prompt: str,
    cid: str,
    sealed: bool,
    out: Path,
) -> str:
    from cursor_sdk import AgentOptions, AsyncAgent, LocalAgentOptions

    t0 = time.time()
    try:
        r = await asyncio.wait_for(
            AsyncAgent.prompt(
                "You are the model under test. Do not use tools. "
                "Read ONLY this message. Reply with the required ANSWER line only.\n\n"
                + prompt,
                AgentOptions(
                    model=model,
                    api_key=api_key,
                    tools=[],
                    local=LocalAgentOptions(cwd=cwd),
                ),
                client=client,
            ),
            timeout=90,
        )
        raw = (r.result or "").strip() or f"ERROR: empty status={r.status}"
        if r.status != "finished" and not raw.startswith("ERROR:"):
            raw = f"ERROR: status={r.status}\n{raw}"
    except TimeoutError:
        raw = "ERROR: timeout 90s"
    except Exception as e:
        raw = f"ERROR: {e}"
    pred, text = parse(cid, raw, sealed=sealed)
    if raw.startswith("ERROR:"):
        text = f"ERROR: {raw}\n"
    out.write_text(text)
    print(f"{out.parent.name} {out.stem} {time.time() - t0:.1f}s -> {pred}", flush=True)
    return pred


async def run(args: argparse.Namespace) -> None:
    from cursor_sdk import AsyncClient

    api_key = os.environ.get("AGENT_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set AGENT_API_KEY (do not commit it).")
    h = json.loads(Path(args.harness).read_text())
    arms = args.arms or list(h["arms"])
    reply_root = RESULTS / f"{Path(args.harness).stem}_replies_{args.tag}"
    reply_root.mkdir(parents=True, exist_ok=True)
    jobs = []
    for arm in arms:
        meta = h["arms"][arm]
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        sealed = bool(meta.get("sealed_answer"))
        for i, p in enumerate(meta["item_paths"]):
            out = out_dir / f"item_{i}.txt"
            if not args.force and out.exists():
                prev = out.read_text()
                if "ERROR:" not in prev and (ANS_SEAL.search(prev) or ANS_PLAIN.search(prev)):
                    print(f"skip {arm} {i}", flush=True)
                    continue
            jobs.append(
                {
                    "prompt": repo_abs(p).read_text(),
                    "cid": meta["ids"][i],
                    "sealed": sealed,
                    "out": out,
                }
            )
    if not jobs:
        print("nothing to run", args.tag, arms)
        return
    empty = tempfile.mkdtemp(prefix="oir-mut-")
    sem = asyncio.Semaphore(args.concurrency)
    async with await AsyncClient.launch_bridge(workspace=empty) as client:

        async def guarded(job: dict) -> None:
            async with sem:
                await one(
                    client=client,
                    model=args.model,
                    api_key=api_key,
                    cwd=empty,
                    **job,
                )

        await asyncio.gather(*(guarded(j) for j in jobs))
    print("done", args.model, args.tag, arms, "n", len(jobs))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("harness")
    ap.add_argument("tag")
    ap.add_argument("model")
    ap.add_argument("arms", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--concurrency", type=int, default=int(os.environ.get("OIR_CONCURRENCY", "4")))
    args = ap.parse_args()
    if not args.model.strip() or " " in args.tag:
        raise SystemExit(
            "Usage: run_iso_agent_harness.py HARNESS TAG MODEL "
            "(TAG=composer25|grok45, MODEL=composer-2.5|grok-4.5)"
        )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
