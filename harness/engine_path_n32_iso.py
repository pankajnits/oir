#!/usr/bin/env python3
"""Engine ceiling for PATH_TRAP n32 iso (no LLM)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "adv_induction_n32_iso_harness.json").read_text())
ANS = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)


def main() -> None:
    """Write gold answers for PATH_TRAP as engine oracle (exact gold from harness)."""
    out = RESULTS / "adv_n32_iso_replies_engine" / "PATH_TRAP"
    out.mkdir(parents=True, exist_ok=True)
    golds = {c["id"]: c for c in H["cases"] if c["arm"] == "PATH_TRAP"}
    for cid, c in golds.items():
        i = c["i"]
        (out / f"item_{i}.txt").write_text(f"ANSWER_SEALED[{cid}]: {c['gold']}\n")
    print("wrote", len(golds), "engine PATH replies")


if __name__ == "__main__":
    main()
