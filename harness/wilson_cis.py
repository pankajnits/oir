#!/usr/bin/env python3
"""Wilson 95% CIs for locked OIR headline arms.

The hardcoded ARMS dict includes older n=12 packaging cells (WTQ_PLAIN_NL 8/8,
OPAQUE_PLAN_ISO_AUTO, …). Those are not Wiki-H5 / Movie-B. Cite results/*.json
for the paper spine.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "wilson_cis.json"


def locked_score(k: int, n: int, missing: int = 0) -> str:
    """Print not_run when every item is missing. Do not cite missing==n as 0/n."""
    if n > 0 and missing >= n:
        return "not_run"
    return f"{k}/{n}"


def wilson(k: int, n: int, z: float = 1.96) -> dict:
    if n <= 0:
        return {"k": k, "n": n, "acc": None, "ci95": None}
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return {
        "k": k,
        "n": n,
        "acc": round(p, 4),
        "ci95": [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)],
        "display": f"{k}/{n} [{max(0.0, centre - half):.2f},{min(1.0, centre + half):.2f}]",
    }


ARMS = {
    "PLAIN_PROG": (12, 12),
    "SEAL_PROG": (12, 12),
    "SEAL_NL": (0, 12),
    "qwen_PLAIN": (12, 12),
    "qwen_SEAL_PROG": (0, 12),
    "qwen_SEAL_NL": (0, 12),
    "SIGMA": (12, 12),
    "SIGMA_PRIME": (12, 12),
    "DEMO_0": (2, 8),
    "DEMO_1": (8, 8),
    "LEGEND": (8, 8),
    "PATH_demo": (8, 8),
    "SYN": (0, 12),
    "LONGCTX_NL": (0, 8),
    "LONGCTX_PROG": (8, 8),
    "SAME_TRAP": (6, 6),
    "CROSS_TRAP": (1, 6),
    "CROSS_TRAP_trap_rate": (5, 6),
    "PATH_TRAP": (6, 6),
    "SAME_TRAP_n24": (24, 24),
    "CROSS_TRAP_n24_auto": (0, 24),
    "CROSS_TRAP_n24_gpt": (24, 24),
    "PATH_TRAP_n24": (24, 24),
    "CEIL_n24": (24, 24),
    "TABLE_PLAIN": (12, 12),
    "TABLE_SEAL_PROG": (12, 12),
    "TABLE_SEAL_NL": (0, 12),
    "JSON_PLAIN": (12, 12),
    "JSON_SEAL_PROG": (12, 12),
    "JSON_SEAL_NL": (0, 12),
    "VAULT_MILD": (12, 12),
    "VAULT_STRICT_PROG": (12, 12),
    "VAULT_STRICT_NL": (0, 12),
    "CEO_PLAIN_NL": (12, 12),
    "CEO_SEAL_NL_auto": (0, 12),
    "WIKI_PLAIN_NL": (12, 12),
    "WIKI_SEAL_NL_auto": (2, 12),
    "WIKI_SEAL_NL_gpt": (0, 12),
    "WIKI_SPAN_NL_auto": (12, 12),
    "WTQ_PLAIN_NL": (8, 8),
    "WTQ_SEAL_NL": (0, 8),
    "OPAQUE_SPAN_NL_auto": (0, 12),
    "OPAQUE_LEGEND_auto": (12, 12),
    "OPAQUE_PROG_auto": (12, 12),
    "WIKI_CF_BM25_n200": (6, 200),
    "WIKI_CF_BM25_leak_n200": (75, 200),
    "WIKI_CF_ROUTER_n200": (200, 200),
    "SPIDER_ENGINE_n200": (191, 200),
    "SPIDER_BM25_n200": (1, 200),
    "SPIDER_SCHEMA_n200": (5, 200),
    "OPAQUE_SPAN_ISO_GPT": (0, 12),
    "OPAQUE_PLAN_ISO_AUTO": (0, 12),
    "WIKI_CF_PLAIN_n32": (32, 32),
    "WIKI_CF_PLAIN_n200": (200, 200),
    "SPIDER_SQL_EXEC_n32": (29, 32),
    "SPIDER_HEURISTIC_n200": (17, 200),
}


def main():
    table = {name: wilson(k, n) for name, (k, n) in ARMS.items()}
    OUT.write_text(json.dumps({"z": 1.96, "arms": table}, indent=2))
    for name, row in table.items():
        print(f"{name:24} {row['display']}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
