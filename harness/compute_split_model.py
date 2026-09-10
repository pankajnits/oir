#!/usr/bin/env python3
"""
Scientific compute model: monolith LLM vs Language + Reasoner split.

Formulas (standard)
-------------------
  Train FLOPs  C ≈ 6 * N * D          (Kaplan/Chinchilla)
  Infer FLOPs  ≈ 2 * N * T            (forward only, T tokens)
  H100 peak    ~ 1e15 FLOP/s FP16 theoretical; use effective util η

Published anchors
----------------------------------------------------
  DeepSeek-V3: 2.788e6 H800-h ≈ $5.6M @ $2/GPU-h (final run only)
  GPT-4 era frontier: ~$78–100M+ compute (Stanford AI Index)
  Small RL reasoner 1.5B: ~$42 on 4×A40 / 24h (Open-RS, arXiv:2503.16219)
  API: GPT-4o ~$2.50/$10 per 1M in/out; 4o-mini ~$0.15/$0.60

OIR implication
---------------
  Language module needs web-scale D_lang.
  Opaque-ID Reasoner needs program/graph D_prog ≪ D_lang
    OR exact SealRouter (GPU≈0 for joins).
  Split removes redundant language modeling from the reasoning path.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "compute_split_model.json"
PAPER = ROOT / "paper" / "IMPACT_COMPUTE.md"

# Hardware assumptions (conservative cloud 2025–26)
H100_FLOPS_EFF = 5e14  # effective train FLOP/s (utilized, not peak)
H100_USD_PER_H = 2.50  # mid cloud on-demand-ish; DeepSeek used $2 H800
A100_USD_PER_H = 1.20


@dataclass
class TrainBudget:
    name: str
    n_params: float
    n_tokens: float
    note: str = ""

    @property
    def flops(self) -> float:
        return 6.0 * self.n_params * self.n_tokens

    @property
    def gpu_hours_h100(self) -> float:
        return self.flops / H100_FLOPS_EFF / 3600.0

    @property
    def usd(self) -> float:
        return self.gpu_hours_h100 * H100_USD_PER_H


@dataclass
class InferBudget:
    name: str
    n_params_active: float
    tokens_per_query: float
    queries_per_day: float
    usd_per_mtok_api: float | None = None  # if API priced

    @property
    def flops_per_day(self) -> float:
        return 2.0 * self.n_params_active * self.tokens_per_query * self.queries_per_day

    @property
    def gpu_hours_per_day(self) -> float:
        # inference often higher util; use same effective for order-of-magnitude
        return self.flops_per_day / (H100_FLOPS_EFF * 1.5) / 3600.0

    @property
    def usd_per_day_gpu(self) -> float:
        return self.gpu_hours_per_day * H100_USD_PER_H

    @property
    def usd_per_day_api(self) -> float | None:
        if self.usd_per_mtok_api is None:
            return None
        mtok = self.tokens_per_query * self.queries_per_day / 1e6
        return mtok * self.usd_per_mtok_api


def fmt_eng(x: float) -> str:
    if x >= 1e12:
        return f"{x/1e12:.2f}e12"
    if x >= 1e9:
        return f"{x/1e9:.2f}e9"
    if x >= 1e6:
        return f"{x/1e6:.2f}e6"
    if x >= 1e3:
        return f"{x/1e3:.2f}e3"
    return f"{x:.2f}"


def main():
    # --- Training scenarios ---
    scenarios = [
        TrainBudget(
            "monolith_frontierish_70B_chinchilla",
            n_params=70e9,
            n_tokens=1.4e12,  # Chinchilla-like
            note="70B × 1.4T tokens (Chinchilla-scale language+reason together)",
        ),
        TrainBudget(
            "monolith_8B_web",
            n_params=8e9,
            n_tokens=2e12,
            note="8B on ~2T web tokens (typical open LM pretrain order)",
        ),
        TrainBudget(
            "language_only_8B_web",
            n_params=8e9,
            n_tokens=2e12,
            note="Language module: same as 8B web LM (talk/compile)",
        ),
        TrainBudget(
            "reasoner_3B_programs",
            n_params=3e9,
            n_tokens=50e9,  # programs/graphs/tools — NOT full web
            note="Reasoner on ~50B program/graph tokens (OIR-relevant corpus)",
        ),
        TrainBudget(
            "reasoner_1p5B_RL_anchor",
            n_params=1.5e9,
            n_tokens=1e9,  # placeholder; real cost from paper $42
            note="Anchor: published small RL reasoner ~$42 / 4×A40 / 24h",
        ),
        TrainBudget(
            "deepseek_v3_reported_scale",
            n_params=37e9,  # active
            n_tokens=14.8e12,
            note="Order-of-mag check vs DeepSeek-V3 2.788M H800-h reported",
        ),
    ]

    train_rows = []
    for s in scenarios:
        train_rows.append(
            {
                "name": s.name,
                "N": s.n_params,
                "D": s.n_tokens,
                "FLOPs_6ND": s.flops,
                "H100_hours_est": round(s.gpu_hours_h100, 1),
                "USD_est_at_2p5": round(s.usd, 0),
                "note": s.note,
            }
        )

    # Split vs monolith training comparison (same language quality target)
    lang = next(s for s in scenarios if s.name == "language_only_8B_web")
    reason = next(s for s in scenarios if s.name == "reasoner_3B_programs")
    mono8 = next(s for s in scenarios if s.name == "monolith_8B_web")
    mono70 = next(s for s in scenarios if s.name == "monolith_frontierish_70B_chinchilla")

    split_train_usd = lang.usd + reason.usd
    # SealRouter exact executor: $0 train
    sealrouter_usd = 0.0

    # --- Inference: 1e6 queries/day enterprise ---
    qpd = 1_000_000
    # Monolith: full model sees long sealed context (waste)
    mono_infer = InferBudget("monolith_70B_api_like", 70e9, tokens_per_query=8000, queries_per_day=qpd, usd_per_mtok_api=6.0)
    # Split: language short compile (2k tok) on 8B + reasoner 1k tok on 3B OR sealrouter
    lang_infer = InferBudget("language_8B_compile", 8e9, 2000, qpd, usd_per_mtok_api=0.4)
    reason_infer = InferBudget("reasoner_3B_exec", 3e9, 1000, qpd, usd_per_mtok_api=0.2)
    # sealrouter: CPU graph walk — treat as $0.001 / 1k queries
    seal_usd_day = qpd * 0.000001  # $1 / 1M queries

    comparison = {
        "assumptions": {
            "train_flops": "C=6ND",
            "H100_effective_FLOP_s": H100_FLOPS_EFF,
            "H100_USD_per_hour": H100_USD_PER_H,
            "caveat": (
                "Order-of-magnitude model for architecture argument — not a lab invoice. "
                "DeepSeek reported 2.788M H800-h / ~$5.6M @ $2; GPT-4 era ~$78–100M+ (AI Index). "
                "Small RL reasoner ~$42 (arXiv:2503.16219)."
            ),
        },
        "train": train_rows,
        "architecture_compare_train_USD": {
            "monolith_70B_chinchilla_est": round(mono70.usd, 0),
            "monolith_8B_web_est": round(mono8.usd, 0),
            "split_Language8B_plus_Reasoner3B_est": round(split_train_usd, 0),
            "split_Language8B_plus_SealRouter_est": round(lang.usd + sealrouter_usd, 0),
            "ratio_monolith70_over_split_sealrouter": round(mono70.usd / max(lang.usd, 1), 1),
            "ratio_monolith8_over_reasoner_alone": round(mono8.usd / max(reason.usd, 1), 1),
            "oir_claim": (
                "If opaque-ID execution does not need web-language pretraining, "
                "Reasoner train tokens collapse from ~1e12 to ~1e10–5e10 (or $0 SealRouter)."
            ),
        },
        "inference_1M_queries_per_day_USD": {
            "monolith_70B_api_like": round(mono_infer.usd_per_day_api or 0, 0),
            "split_lang8B_plus_reasoner3B_api_like": round(
                (lang_infer.usd_per_day_api or 0) + (reason_infer.usd_per_day_api or 0), 0
            ),
            "split_lang8B_plus_SealRouter": round((lang_infer.usd_per_day_api or 0) + seal_usd_day, 0),
            "tokens_assumption": "mono 8k tok/q; lang compile 2k; reasoner 1k; SealRouter ~free",
        },
        "published_anchors": {
            "DeepSeek_V3_H800_hours": 2.788e6,
            "DeepSeek_V3_USD_at_2": 5.576e6,
            "GPT4_era_USD_AI_Index": "78e6–100e6+",
            "Llama_3_1_family_H100_hours": {"8B": 1.46e6, "70B": 7.0e6, "405B": 30.84e6},
            "small_RL_reasoner_USD": 42,
            "small_RL_reasoner_cite": "arXiv:2503.16219 Open-RS ~4×A40 24h",
        },
        "energy_carbon_see": "results/compute_energy_carbon.json",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(comparison, indent=2))

    # Paper markdown
    PAPER.write_text(
        f"""# Impact: GPU / training / inference — Language vs Reasoner split

Date: 2026-07-28  
Status: **order-of-magnitude scientific cost model** (reproducible script).  
Script: `harness/compute_split_model.py` → `results/compute_split_model.json`

## Why this matters for OIR

Our lab result: **free sealed NL fails; opaque-ID programs / SealRouter succeed.**

That implies the expensive part of today's stack — **web-scale language modeling** — is the
wrong compute sink for the *reasoning* path under opacity. A Reasoner can train on
**programs/graphs** (or be an exact executor with **$0 GPU train**).

## Standard formulas

| Quantity | Formula |
|----------|---------|
| Train FLOPs | \\(C \\approx 6ND\\) (Kaplan / Chinchilla) |
| Infer FLOPs | \\(\\approx 2NT\\) forward |
| GPU-hours | \\(C / (\\eta \\cdot \\mathrm{{FLOP/s}})\\) |

Effective H100 train throughput in this model: **{H100_FLOPS_EFF:.0e} FLOP/s**, **${H100_USD_PER_H}/h**.

## Published anchors (not our runs)

| Anchor | Number | Source |
|--------|--------|--------|
| DeepSeek-V3 full train | **2.788M H800-h ≈ $5.6M** @ $2/h | DeepSeek-V3 report (final run only) |
| GPT-4-class frontier | **~$78–100M+** compute | Stanford AI Index 2025 |
| Small RL reasoner (1.5B) | **~$42** / 4×A40 / 24h | Open-RS, arXiv:2503.16219 |
| GPT-4o API | ~$2.50 / $10 per 1M in/out | public pricing 2026 |

## Model estimates (this script)

### Training USD (order-of-mag)

| Architecture | Est. train USD |
|--------------|----------------|
| Monolith 70B × 1.4T (Chinchilla-like) | **${mono70.usd:,.0f}** |
| Monolith 8B × 2T web | **${mono8.usd:,.0f}** |
| Split: Language 8B×2T + Reasoner 3B×50B programs | **${split_train_usd:,.0f}** |
| Split: Language 8B×2T + **SealRouter** (exact) | **${lang.usd:,.0f}** |

Ratio monolith-70B / (Language+SealRouter) ≈ **{mono70.usd/max(lang.usd,1):.0f}×** more train compute on the language-bloated path.

Reasoner-alone vs same-size web LM: program corpus **~40× fewer tokens** than 2T web
(50B vs 2T) → Reasoner train FLOPs drop by that factor if N fixed.

### Inference USD / day @ 1M queries

| Path | Est. $/day (API-like) |
|------|------------------------|
| Monolith 70B, 8k tok/query | **${mono_infer.usd_per_day_api:,.0f}** |
| Language 8B (2k) + Reasoner 3B (1k) | **${(lang_infer.usd_per_day_api or 0)+(reason_infer.usd_per_day_api or 0):,.0f}** |
| Language 8B (2k) + SealRouter | **${(lang_infer.usd_per_day_api or 0)+seal_usd_day:,.0f}** |

## Scientific claim (compute)

> If OIR is right — reasoning under opacity is **program execution on IDs**, not
> language modeling — then **marginal GPU for Reasoner** should track program/graph
> data (or be zero for SealRouter), while Language absorbs web-scale pretrain.
> Monolithic models pay language FLOPs on every reasoning token; the split stops that.

## What would falsify the cost story

- Opaque-ID Reasoner still needs near-web-scale D to match binder accuracy
- SealRouter cannot cover the query family (then neural Reasoner cost rises)
- Compile (Language) dominates tokens so split saves little at inference

## Creative research next (hard work)

1. **Train a tiny opaque-ID Reasoner** (≤1.5B) only on synthetic sealed PATH/DSL —
   measure GPU-hours vs accuracy on SEAL-Bench (we already have the harness).
2. **IsoFLOP curves**: Language-only vs Reasoner-only vs joint on sealed vs plaintext.
3. **Energy / carbon**: convert GPU-h → kWh with published PUE for the paper appendix.

Re-run: `python3 harness/compute_split_model.py`
"""
    )
    print(json.dumps(comparison["architecture_compare_train_USD"], indent=2))
    print(json.dumps(comparison["inference_1M_queries_per_day_USD"], indent=2))
    print("wrote", OUT, PAPER)


if __name__ == "__main__":
    main()
