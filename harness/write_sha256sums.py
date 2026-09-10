#!/usr/bin/env python3
"""Write results/SHA256SUMS over every locked results/*.json (sorted paths)."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = RESULTS / "SHA256SUMS"


def main() -> None:
    files = sorted(p for p in RESULTS.glob("*.json") if p.is_file())
    lines = []
    for p in files:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        lines.append(f"{digest}  {p.name}")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(files)} json files)")


if __name__ == "__main__":
    main()
