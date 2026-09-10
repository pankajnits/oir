#!/usr/bin/env python3
"""Run pending OpenAI free-form MUTs that the paper marked n.r. / not_run.

Requires OPENAI_API_KEY. Does not write the key to disk.

  python3 harness/run_openai_pending.py [suite...]
  suites: xfer_nobind hop4 excel finqa_wtq   (default: all)
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
RESULTS = ROOT / "results"
ANS = re.compile(r"ANSWER_(?:SEALED|NUM)\[([^\]]+)\]:\s*([^\n]+)", re.I)
MODEL = os.environ.get("OIR_MODEL", "gpt-5.6-sol")


def complete(client: OpenAI, prompt: str, *, max_tokens: int = 2048) -> str:
    last: Exception | None = None
    for attempt in range(6):
        try:
            r = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_tokens,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            last = e
            wait = min(90.0, 1.8**attempt)
            print(f"  retry {attempt+1}: {e} (sleep {wait:.1f}s)", flush=True)
            time.sleep(wait)
    raise RuntimeError(last)


def write_reply(path: Path, cid: str | None, raw: str, *, numeric: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    ms = list(ANS.finditer(raw))
    if cid and ms:
        # keep last match for this cid if present
        for m in reversed(ms):
            if m.group(1) == cid:
                pred = m.group(2).strip()
                path.write_text(f"ANSWER_{'NUM' if numeric else 'SEALED'}[{cid}]: {pred}\n# raw_tail\n{raw[-1200:]}\n")
                return pred
        pred = ms[-1].group(2).strip()
        path.write_text(f"ANSWER_{'NUM' if numeric else 'SEALED'}[{cid}]: {pred}\n# raw_tail\n{raw[-1200:]}\n")
        return pred
    if cid:
        atom = re.search(r"\b(E[0-9a-f]{12})\b", raw, re.I)
        if atom and not numeric:
            pred = atom.group(1)
            path.write_text(f"ANSWER_SEALED[{cid}]: {pred}\n# raw\n{raw[:2500]}\n")
            return pred
        if re.search(r"\bUNKNOWN\b", raw, re.I):
            path.write_text(f"ANSWER_SEALED[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n")
            return "UNKNOWN"
        path.write_text(f"ANSWER_SEALED[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n")
        return "UNKNOWN"
    # batch: keep full model text (scorer parses all ANSWER_* lines)
    path.write_text(raw + ("\n" if not raw.endswith("\n") else ""))
    return f"{len(ms)}_answers"


def run_xfer_nobind(client: OpenAI) -> None:
    reply = RESULTS / "seal_layer_xfer_replies_gpt56"
    for fam in ("COMPLEX", "REAL"):
        for i in range(6):
            cid = f"XFER_{fam}_NOBIND_{i}"
            out = reply / f"{cid}.txt"
            if out.exists() and "ERROR:" not in out.read_text() and ANS.search(out.read_text()):
                print(f"skip {cid}")
                continue
            prompt = (ROOT / "runs" / "seal_layer_xfer" / fam / "NOBIND" / f"item_{i}" / "prompt.txt").read_text()
            t0 = time.time()
            try:
                raw = complete(client, prompt, max_tokens=256)
            except Exception as e:
                raw = f"ERROR: {e}"
            pred = write_reply(out, cid, raw)
            print(f"{cid} {time.time()-t0:.1f}s -> {pred}", flush=True)


def run_hop4(client: OpenAI) -> None:
    reply = RESULTS / "hop4_replies_gpt56"
    H = json.loads((RESULTS / "hop4_harness.json").read_text())
    for c in H["cases"]:
        if c["arm"] not in ("DEMO_0", "PATH"):
            continue
        arm = c["arm"]
        if arm == "DEMO_0":
            prompt_path = ROOT / c["path"]
            out = reply / "DEMO_0" / f"item_{c['id'].split('_')[-1]}.txt"
            # ids like HOP4_DEMO_0_0
            idx = c["id"].rsplit("_", 1)[-1]
            out = reply / "DEMO_0" / f"item_{idx}.txt"
            if out.exists() and "ERROR:" not in out.read_text() and ANS.search(out.read_text()):
                print(f"skip {c['id']}")
                continue
            t0 = time.time()
            try:
                raw = complete(client, prompt_path.read_text(), max_tokens=256)
            except Exception as e:
                raw = f"ERROR: {e}"
            pred = write_reply(out, c["id"], raw)
            print(f"{c['id']} {time.time()-t0:.1f}s -> {pred}", flush=True)
        else:
            # one batch for all PATH
            out = reply / "PATH" / "BATCH.txt"
            if out.exists() and "ERROR:" not in out.read_text() and len(ANS.findall(out.read_text())) >= 6:
                print("skip PATH batch")
                return
            t0 = time.time()
            try:
                raw = complete(client, (ROOT / "runs/hop4/PATH_BATCH/BATCH.txt").read_text(), max_tokens=1024)
            except Exception as e:
                raw = f"ERROR: {e}"
            write_reply(out, None, raw)
            print(f"PATH batch {time.time()-t0:.1f}s -> {len(ANS.findall(raw))} answers", flush=True)
            return


def run_excel(client: OpenAI) -> None:
    mapping = {
        "WIKI_NL": ROOT / "runs/real_docs/WIKI_XLSX_NL_ONLY/BATCH.txt",
        "WIKI_PROG": ROOT / "runs/real_docs/WIKI_XLSX_PROG_ONLY/BATCH.txt",
        "OD500_NL": ROOT / "runs/real_docs/OD500_XLSX_NL_ONLY/BATCH.txt",
        "OD500_PROG": ROOT / "runs/real_docs/OD500_XLSX_PROG_ONLY/BATCH.txt",
    }
    reply = RESULTS / "real_docs_replies"
    reply.mkdir(parents=True, exist_ok=True)
    for key, src in mapping.items():
        out = reply / f"{key}_gpt56.txt"
        if out.exists() and "ERROR:" not in out.read_text() and len(ANS.findall(out.read_text())) >= 8:
            print(f"skip excel {key}")
            continue
        t0 = time.time()
        try:
            raw = complete(client, src.read_text(), max_tokens=2048)
        except Exception as e:
            raw = f"ERROR: {e}"
        write_reply(out, None, raw)
        print(f"excel {key} {time.time()-t0:.1f}s -> {len(ANS.findall(raw))} answers", flush=True)


def run_finqa_wtq(client: OpenAI) -> None:
    forms = {
        "FQ_NL": ROOT / "runs/real_complex_verify/FQ_NL_ONLY/BATCH.txt",
        "FQ_PROG": ROOT / "runs/real_complex_verify/FQ_PROG_ONLY/BATCH.txt",
        "FQ_FOLLOW": ROOT / "runs/real_complex_verify/FQ_FOLLOW_ONLY/BATCH.txt",
        "WTQ_NL": ROOT / "runs/real_complex_verify/WTQ_NL_ONLY/BATCH.txt",
        "WTQ_DSL": ROOT / "runs/real_complex_verify/WTQ_DSL_ONLY/BATCH.txt",
    }
    reply = RESULTS / "real_complex_verify_replies"
    reply.mkdir(parents=True, exist_ok=True)
    for form, src in forms.items():
        out = reply / f"{form}_gpt56.txt"
        if out.exists() and "ERROR:" not in out.read_text() and len(ANS.findall(out.read_text())) >= 2:
            print(f"skip {form}")
            continue
        t0 = time.time()
        print(f"start {form} (~{src.stat().st_size // 4} tok)...", flush=True)
        try:
            raw = complete(client, src.read_text(), max_tokens=4096)
        except Exception as e:
            raw = f"ERROR: {e}"
        write_reply(out, None, raw)
        print(f"{form} {time.time()-t0:.1f}s -> {len(ANS.findall(raw))} answers", flush=True)


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY")
    suites = sys.argv[1:] or ["xfer_nobind", "hop4", "excel", "finqa_wtq"]
    client = OpenAI()
    print("model", MODEL, "suites", suites, flush=True)
    if "xfer_nobind" in suites:
        run_xfer_nobind(client)
    if "hop4" in suites:
        run_hop4(client)
    if "excel" in suites:
        run_excel(client)
    if "finqa_wtq" in suites:
        run_finqa_wtq(client)
    print("done", flush=True)


if __name__ == "__main__":
    main()
