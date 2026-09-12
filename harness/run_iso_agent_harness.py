#!/usr/bin/env python3
"""Isolation MUT (composer-2.5 / grok-4.5) through Cursor's Python SDK.

No tools, empty cwd: the model cannot read gold JSON. Skips final reply files.

  AGENT_API_KEY=... python3 harness/run_iso_agent_harness.py \\
      results/factorial_2x2_iso_harness.json composer25 composer-2.5 [arm...] \\
      [--preamble cursor|none] [--retry-empty] [--force]

``CURSOR_API_KEY`` is accepted as a fallback for ``AGENT_API_KEY``.
Do not reuse locked tags (``composer25``, ``grok45``) for new suites.

Access route (disclose in papers): both models are called via Cursor's agent
bridge (``cursor_sdk.AsyncAgent``), not a vendor chat API. Requires Cursor's
Python SDK (``pip install -e '.[cursor]'``).

``--preamble cursor`` (default, reproduces locked cells) prefixes every prompt
with an instruction that OpenAI cells never received. ``--preamble none``
sends the prompt file verbatim, matching run_openai_iso_harness.py.

Review fixes: empty replies are NO_OUTPUT (not UNKNOWN); a JSON sidecar keeps
the full reply, status, preamble mode, model and timestamp.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from paths import repo_abs  # noqa: E402
from reply_parse import classify, is_final, parse  # noqa: E402

RESULTS = ROOT / "results"
OK_STATUSES = {"finished", "completed"}
CURSOR_PREAMBLE = (
    "You are the model under test. Do not use tools. "
    "Read ONLY this message. Reply with the required ANSWER line only.\n\n"
)


def resolve_api_key() -> str:
    key = (
        os.environ.get("AGENT_API_KEY", "").strip()
        or os.environ.get("CURSOR_API_KEY", "").strip()
    )
    if not key:
        raise SystemExit("Set AGENT_API_KEY or CURSOR_API_KEY (do not commit it).")
    return key


def _status_error_message(ev) -> str | None:
    if getattr(ev, "type", None) != "status":
        return None
    st = str(getattr(ev, "status", "")).upper()
    if st != "ERROR":
        return None
    msg = (getattr(ev, "message", None) or "").strip()
    return msg or None


def _billing_blocked(raw: str) -> bool:
    return "unpaid invoice" in (raw or "").lower()


def persist_reply(out: Path, *, text: str, sidecar: dict) -> None:
    out.write_text(text)
    out.with_suffix(".json").write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n")


def discard_reply(out: Path) -> None:
    out.unlink(missing_ok=True)
    out.with_suffix(".json").unlink(missing_ok=True)


def settle_canary(first: dict, out: Path) -> None:
    """Persist a successful canary, or discard any partial file and abort."""
    raw = first.get("raw") or ""
    if _billing_blocked(raw) or raw.startswith("ERROR:"):
        discard_reply(out)
        if _billing_blocked(raw):
            raise SystemExit(
                "Cursor API blocked (unpaid invoice). Pay at https://cursor.com/dashboard "
                "then re-run; no canary reply was written."
            )
        raise SystemExit(
            "canary failed (not scoring the rest; no reply written): " + raw[:400]
        )
    persist_reply(out, text=first["text"], sidecar=first["sidecar"])


def _require_sdk():
    try:
        import cursor_sdk  # noqa: F401
    except ImportError as e:  # pragma: no cover - environment dependent
        raise SystemExit(
            "cursor_sdk is required for Composer/Grok cells (Cursor agent bridge). "
            "Install Cursor's Python SDK; see Cursor's SDK docs."
        ) from e


async def one(*, client, model: str, api_key: str, cwd: str, prompt: str, cid: str,
              sealed: bool, out: Path, preamble: str, write: bool = True) -> dict:
    from cursor_sdk import AgentOptions, AsyncAgent, LocalAgentOptions

    t0 = time.time()
    status = None
    err_note = None
    sent = (CURSOR_PREAMBLE if preamble == "cursor" else "") + prompt

    async def _call() -> str:
        nonlocal status, err_note
        agent = await AsyncAgent.create(
            AgentOptions(model=model, api_key=api_key, tools=[],
                         local=LocalAgentOptions(cwd=cwd)),
            client=client,
        )
        try:
            run = await agent.send(sent)
            async for ev in run.messages():
                note = _status_error_message(ev)
                if note:
                    err_note = note
            r = await run.wait()
            status = r.status
            raw = (r.result or "").strip()
            st = str(status or "").lower()
            if err_note and not raw:
                return f"ERROR: {err_note}"
            if not raw and st not in OK_STATUSES:
                return f"ERROR: empty status={status}"
            if st not in OK_STATUSES and not raw.startswith("ERROR:"):
                extra = f" ({err_note})" if err_note else ""
                return f"ERROR: status={status}{extra}\n{raw}"
            return raw
        finally:
            await agent.close()

    try:
        raw = await asyncio.wait_for(_call(), timeout=90)
    except TimeoutError:
        raw = "ERROR: timeout 90s"
    except Exception as e:
        raw = f"ERROR: {e}"
    pred, text = parse(cid, raw, sealed=sealed)
    if raw.startswith("ERROR:"):
        text = f"ERROR: {raw}\n"
    sidecar = {
        "id": cid, "pred": pred, "raw": raw, "status": status, "model": model,
        "preamble": preamble, "elapsed_s": round(time.time() - t0, 3),
        "utc": datetime.now(timezone.utc).isoformat(), "route": "cursor_sdk.AsyncAgent",
        "error": err_note,
    }
    if write:
        persist_reply(out, text=text, sidecar=sidecar)
    print(f"{out.parent.name} {out.stem} {time.time() - t0:.1f}s -> {pred}", flush=True)
    return {"pred": pred, "raw": raw, "status": status, "text": text, "sidecar": sidecar}


async def run(args: argparse.Namespace) -> None:
    _require_sdk()
    from cursor_sdk import AsyncClient

    api_key = resolve_api_key()
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
                if is_final(prev) and not (args.retry_empty and classify(prev) == "legacy_empty"):
                    print(f"skip {arm} {i}", flush=True)
                    continue
            jobs.append({"prompt": repo_abs(p).read_text(), "cid": meta["ids"][i],
                         "sealed": sealed, "out": out})
    if not jobs:
        print("nothing to run", args.tag, arms)
        return
    empty = tempfile.mkdtemp(prefix="oir-mut-")
    sem = asyncio.Semaphore(args.concurrency)
    async with await AsyncClient.launch_bridge(workspace=empty) as client:

        async def guarded(job: dict) -> dict:
            async with sem:
                return await one(client=client, model=args.model, api_key=api_key,
                                 cwd=empty, preamble=args.preamble, **job)

        first_job = jobs[0]
        async with sem:
            first = await one(client=client, model=args.model, api_key=api_key,
                              cwd=empty, preamble=args.preamble, write=False, **first_job)
        settle_canary(first, first_job["out"])
        if len(jobs) > 1:
            await asyncio.gather(*(guarded(j) for j in jobs[1:]))
    print("done", args.model, args.tag, arms, "n", len(jobs), "preamble", args.preamble)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("harness")
    ap.add_argument("tag")
    ap.add_argument("model")
    ap.add_argument("arms", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--retry-empty", action="store_true")
    ap.add_argument("--preamble", choices=("cursor", "none"), default="cursor")
    ap.add_argument("--concurrency", type=int, default=int(os.environ.get("OIR_CONCURRENCY", "4")))
    args = ap.parse_args()
    if not args.model.strip() or " " in args.tag:
        raise SystemExit("Usage: run_iso_agent_harness.py HARNESS TAG MODEL "
                         "(TAG=composer25|grok45, MODEL=composer-2.5|grok-4.5)")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
