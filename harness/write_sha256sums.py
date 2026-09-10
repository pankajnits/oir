#!/usr/bin/env python3
"""Write results/SHA256SUMS over git-tracked results/*.json (sorted names).

Skips gitignored JSON (currently results/longctx_1m*), so
``shasum -c results/SHA256SUMS`` succeeds on a fresh clone.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = RESULTS / "SHA256SUMS"


def tracked_result_json() -> list[Path]:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "results/"],
        capture_output=True,
    )
    if r.returncode == 0:
        names = [n for n in r.stdout.decode().split("\0") if n.endswith(".json")]
        return sorted(ROOT / n for n in names if (ROOT / n).is_file())
    files = sorted(p for p in RESULTS.glob("*.json") if p.is_file())
    return [p for p in files if not p.name.startswith("longctx_1m")]


def main() -> None:
    files = tracked_result_json()
    lines = []
    for p in files:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        rel = p.resolve().relative_to(ROOT.resolve()).as_posix()
        lines.append(f"{digest}  {rel}")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(files)} tracked json files)")


if __name__ == "__main__":
    main()
