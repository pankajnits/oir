#!/usr/bin/env python3
"""Write results/SHA256SUMS over git-tracked results JSON and reply .txt files.

Covers locked summaries, reply sidecars, and per-item replies. Skips
gitignored JSON (currently results/longctx_1m*) and the lockfile itself, so
``shasum -c results/SHA256SUMS`` succeeds on a fresh clone.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = RESULTS / "SHA256SUMS"
EVIDENCE_SUFFIXES = (".json", ".txt")


def tracked_result_files() -> list[Path]:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "results/"],
        capture_output=True,
    )
    if r.returncode == 0:
        names = [
            n
            for n in r.stdout.decode().split("\0")
            if n.endswith(EVIDENCE_SUFFIXES) and Path(n).name != "SHA256SUMS"
        ]
        return sorted(ROOT / n for n in names if (ROOT / n).is_file())
    files = sorted(
        p for p in RESULTS.rglob("*") if p.is_file() and p.suffix in EVIDENCE_SUFFIXES
    )
    return [p for p in files if not p.name.startswith("longctx_1m")]


def main() -> None:
    files = tracked_result_files()
    lines = []
    for p in files:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        rel = p.resolve().relative_to(ROOT.resolve()).as_posix()
        lines.append(f"{digest}  {rel}")
    OUT.write_text("\n".join(lines) + "\n")
    n_json = sum(1 for p in files if p.suffix == ".json")
    n_txt = sum(1 for p in files if p.suffix == ".txt")
    print(f"wrote {OUT} ({n_json} json, {n_txt} txt)")


if __name__ == "__main__":
    main()
