#!/usr/bin/env python3
"""Build paper/appendix_prompts.md — one sample prompt path per suite."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
OUT = ROOT / "paper" / "appendix_prompts.md"

PRIORITY = [
    "ceiling_three_arm",
    "rename_equivariance",
    "demo_induction",
    "adv_induction",
    "synonym_enrich",
    "longctx",
    "partial_handles_scaled",
    "plain_relcol_isolated",
]


def first_prompt(suite: Path) -> Path | None:
    for name in ("prompt.txt", "BATCH.txt"):
        hits = list(suite.rglob(name))
        if hits:
            return sorted(hits)[0]
    txts = sorted(suite.rglob("*.txt"))
    return txts[0] if txts else None


def main():
    lines = [
        "# Appendix — sample prompt paths",
        "",
        "One representative MUT prompt per suite (relative to repo root).",
        "Full trees live under `runs/<suite>/`.",
        "",
        "| Suite | Sample prompt |",
        "|-------|---------------|",
    ]
    suites = {p.name: p for p in RUNS.iterdir() if p.is_dir()}
    ordered = [s for s in PRIORITY if s in suites] + sorted(
        k for k in suites if k not in PRIORITY
    )
    for name in ordered:
        p = first_prompt(suites[name])
        if not p:
            lines.append(f"| `{name}` | *(no prompt)* |")
            continue
        rel = p.relative_to(ROOT)
        lines.append(f"| `{name}` | `{rel}` |")
    OUT.write_text("\n".join(lines) + "\n")
    print("wrote", OUT, "rows", len(ordered))


if __name__ == "__main__":
    main()
