#!/usr/bin/env python3
"""Build paper figures from locked results/*.json.

TeX ships fig1, fig3, and fig7. fig2/fig4/fig5/fig6 are written here for
the figures/ archive and are not included in main.tex.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = ROOT / "paper" / "figures"


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def frac(s: str) -> float:
    a, b = s.split("/")
    return int(a) / int(b)


def score_of(v) -> str:
    return v["score"] if isinstance(v, dict) else v


def set_acc_axis(ax) -> None:
    """Accuracy is in [0, 1]; do not draw a 1.2 headroom band."""
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0, 0.5, 1.0])


def label_bar(ax, bar, text: str, value: float, *, fontsize: int = 8) -> None:
    if value >= 0.88:
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            max(value - 0.045, 0.02),
            text,
            ha="center",
            va="top",
            fontsize=fontsize,
            color="white",
            clip_on=False,
        )
    else:
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            min(value + 0.03, 0.96),
            text,
            ha="center",
            va="bottom",
            fontsize=fontsize,
            clip_on=False,
        )


def load_ceiling(name: str) -> dict:
    d = json.loads((RESULTS / name).read_text())
    if "summary" in d:
        return d["summary"]
    # qwen pilot uses flat keys
    return {
        "PLAIN_PROG": d["PLAIN_PROG"],
        "SEAL_PROG": d.get("SEAL_PROG", d.get("SEAL_PROG_percase")),
        "SEAL_NL": d.get("SEAL_NL", d.get("SEAL_NL_percase")),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fact = json.loads((RESULTS / "factorial_2x2_iso_gpt56.json").read_text())["summary"]
    ident_leg = json.loads((RESULTS / "seal_layer_legend_small_n32_harness_gpt56.json").read_text())["summary"]
    ident_iso = json.loads((RESULTS / "opaque_iso_json_n32_harness_gpt56.json").read_text())["summary"]
    adv = json.loads((RESULTS / "adv_induction_n32_iso_gpt56.json").read_text())["summary"]
    rename = json.loads((RESULTS / "rename_equivariance_results.json").read_text())["summary"]

    def _one_panel(path_stem: str, *, figsize, ylabel: bool = True):
        fig, ax = plt.subplots(figsize=figsize, constrained_layout=True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if ylabel:
            ax.set_ylabel("Exact accuracy")
        return fig, ax

    fact200 = json.loads((RESULTS / "factorial_2x2_iso_n200_gpt56n200.json").read_text())["summary"]
    labels = ["English\nunique", "English\ntwo-path", "Opaque\nunique", "Opaque\ntwo-path"]
    arms = ["ENG_UNIQUE", "ENG_AMBIG", "OPAQUE_UNIQUE", "OPAQUE_AMBIG"]

    def stacked_2x2(ax, summary, title, *, ylabel: bool, legend: bool) -> None:
        golds, decoys, unks = [], [], []
        for a in arms:
            row = summary[a]
            n = int(score_of(row).split("/")[1])
            g = int(score_of(row).split("/")[0])
            d = int(row.get("decoy", 0) or 0)
            u = int(row.get("unknown", 0) or 0)
            golds.append(g / n)
            decoys.append(d / n)
            unks.append(u / n)
        x = np.arange(len(labels))
        ax.bar(x, golds, color="#2a6f6f", width=0.72, edgecolor="#1a1a1a", linewidth=0.6, label="Gold")
        ax.bar(x, decoys, bottom=golds, color="#c47a2c", width=0.72, edgecolor="#1a1a1a", linewidth=0.6, label="Decoy")
        ax.bar(
            x,
            unks,
            bottom=np.array(golds) + np.array(decoys),
            color="#c8c8c8",
            width=0.72,
            edgecolor="#1a1a1a",
            linewidth=0.6,
            label="UNKNOWN",
        )
        for i, a in enumerate(arms):
            k_i, n_i = (int(part) for part in score_of(summary[a]).split("/"))
            lo, hi = wilson_interval(k_i, n_i)
            ax.errorbar(
                x[i],
                golds[i],
                yerr=[[golds[i] - lo], [hi - golds[i]]],
                fmt="none",
                ecolor="#111",
                capsize=3,
                elinewidth=0.9,
                zorder=4,
            )
            if golds[i] < 0.5:
                y_txt, va, col = max(golds[i] * 0.52, 0.03), "center", "white"
            elif golds[i] < 0.88:
                y_txt, va, col = min(golds[i] + 0.06, 0.92), "bottom", "#111"
            else:
                y_txt, va, col = golds[i] - 0.08, "top", "white"
            ax.text(x[i], y_txt, f"{k_i}/{n_i}", ha="center", va=va, fontsize=7.5, color=col, zorder=5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        set_acc_axis(ax)
        ax.set_title(title, fontsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if ylabel:
            ax.set_ylabel("Exact accuracy")
        if legend:
            ax.legend(frameon=False, loc="upper right", fontsize=7.5)

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.35), constrained_layout=True, sharey=True)
    stacked_2x2(axes[0], fact, "n=32 discovery", ylabel=True, legend=False)
    stacked_2x2(axes[1], fact200, "n=200 city-typed", ylabel=False, legend=True)
    fig.savefig(OUT / "fig1_matched_2x2.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig1_matched_2x2.png", dpi=200, bbox_inches="tight")
    plt.close()

    fig, ax = _one_panel("fig4_binding", figsize=(6.6, 3.35))
    labs = ["Schema\nlist", "English\nprotocol", "Same σ\nsilent", "Equality\nrecipe", "Match\nbroken"]
    scores = [
        score_of(ident_leg["LEGEND"]),
        score_of(ident_leg["META"]),
        score_of(ident_iso["ISO_SILENT"]),
        score_of(ident_iso["ISO_RULE"]),
        score_of(ident_iso["NS_SILENT"]),
    ]
    vals = [frac(s) for s in scores]
    # Teal = exact-match gold (including the 6/32 silent cell). Red = 0/32.
    # Do not reuse fig1's decoy orange here: silent 6/32 is gold, not decoy.
    colors = ["#b33a3a", "#2a6f6f", "#2a6f6f", "#2a6f6f", "#b33a3a"]
    x = np.arange(len(labs))
    bars = ax.bar(x, vals, color=colors, width=0.72, edgecolor="#1a1a1a", linewidth=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labs, fontsize=7.5)
    set_acc_axis(ax)
    ax.set_title("No written hop (OpenAI JSON, n=32)")
    for b, s, v in zip(bars, scores, vals):
        label_bar(ax, b, s, v, fontsize=7)
    fig.savefig(OUT / "fig4_binding.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig4_binding.png", dpi=200, bbox_inches="tight")
    # Not included in main.tex (OpenAI row of Table tab:ident32).
    plt.close()

    fig, ax = _one_panel("fig3_dualpath", figsize=(5.6, 3.35))
    labs = ["Matched\nrelation", "Novel\n(asymmetric)", "Explicit\nplan"]
    scores = [adv["SAME_TRAP"]["score"], adv["CROSS_TRAP"]["score"], adv["PATH_TRAP"]["score"]]
    vals = [frac(s) for s in scores]
    colors = ["#2a6f6f", "#b33a3a", "#2a6f6f"]
    bars = ax.bar(labs, vals, color=colors, width=0.65, edgecolor="#1a1a1a", linewidth=0.6)
    set_acc_axis(ax)
    ax.set_title("Dual-path (synthetic, OpenAI, n=32)")
    for b, s, v in zip(bars, scores, vals):
        label_bar(ax, b, s, v, fontsize=9)
    ax.text(1.0, 0.48, f"decoy {adv['CROSS_TRAP']['trap_rate']}", ha="center", fontsize=8, color="#8a2020")
    fig.savefig(OUT / "fig3_dualpath.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig3_dualpath.png", dpi=200, bbox_inches="tight")
    plt.close()

    # Fig 2: English two-path vs opaque unique vs opaque two-path (not the CEO three-arm).
    models = [
        ("Composer 2.5", "factorial_2x2_iso_composer25.json", "#2a6f6f"),
        ("OpenAI", "factorial_2x2_iso_gpt56.json", "#3d7ea6"),
        ("Grok 4.5", "factorial_2x2_iso_grok45.json", "#5a6b4a"),
    ]
    arm_keys = ["ENG_AMBIG", "OPAQUE_UNIQUE", "OPAQUE_AMBIG"]
    arm_labels = ["English two-path", "Opaque unique", "Opaque two-path"]
    series = []
    for label, fname, color in models:
        s = load_ceiling(fname)
        series.append(
            (
                label,
                [frac(score_of(s[a])) for a in arm_keys],
                [score_of(s[a]) for a in arm_keys],
                color,
            )
        )

    fig, ax = plt.subplots(figsize=(8.8, 3.55), constrained_layout=True)
    x = np.arange(len(arm_keys))
    n = len(series)
    w = 0.8 / n
    for i, (label, vals, texts, color) in enumerate(series):
        offset = (i - (n - 1) / 2) * w
        bars = ax.bar(x + offset, vals, w * 0.92, label=label, color=color, edgecolor="#1a1a1a", lw=0.5)
        for b, t, v in zip(bars, texts, vals):
            label_bar(ax, b, t, v, fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(arm_labels)
    set_acc_axis(ax)
    ax.set_ylabel("Exact accuracy")
    ax.set_title("Wiki-H5: English two-path vs opaque unique vs opaque two-path (n=32)")
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    # Not included in main.tex / oir-arxiv.zip (Table 3 already reports these cells).
    fig.savefig(OUT / "fig2_opaque_paths.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig2_opaque_paths.png", dpi=200, bbox_inches="tight")
    plt.close()

    fig, ax = plt.subplots(figsize=(4.8, 3.2), constrained_layout=True)
    labs = ["Plan under key 1", "Plan under key 2", "Both pair-correct"]
    scores = [rename["SIGMA"], rename["SIGMA_PRIME"], rename["paired_both_ok"]]
    vals = [frac(s) for s in scores]
    bars = ax.bar(labs, vals, color="#2a6f6f", width=0.55, edgecolor="#1a1a1a", lw=0.6)
    set_acc_axis(ax)
    ax.set_ylabel("Exact accuracy")
    ax.set_title("Join-plan rename equivariance (two HMAC keys)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for b, s, v in zip(bars, scores, vals):
        label_bar(ax, b, s, v, fontsize=9)
    if rename.get("golds_differ_all"):
        ax.text(0.5, -0.22, "Gold answers differ on every pair", transform=ax.transAxes, ha="center", fontsize=8, color="#444")
    fig.savefig(OUT / "fig6_rename_equivariance.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig6_rename_equivariance.png", dpi=200, bbox_inches="tight")
    # Not included in main.tex (rename 12/12 is packaging prose).
    plt.close()

    # Fig 5: opacity × binder 2×2 (real Q)
    auto = json.loads((RESULTS / "realqa_2x2_auto.json").read_text())
    gpt = json.loads((RESULTS / "realqa_2x2_gpt56.json").read_text())
    arms4 = ["PLAIN_NL", "PLAIN_PROG", "SEAL_PROG", "SEAL_NL"]
    panels = [
        ("CEO–HQ (Composer 2.5)", auto["families"]["ceo"]["summary"], "#2a6f6f"),
        ("2Wiki (Composer 2.5)", auto["families"]["wiki"]["summary"], "#2a6f6f"),
        ("2Wiki (OpenAI)", gpt["families"]["wiki"]["summary"], "#3d5a80"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.5), constrained_layout=True)
    for ax, (title, summary, color) in zip(axes, panels):
        texts = [summary[a]["score"] for a in arms4]
        vals = [frac(t) for t in texts]
        cols = [color, color, color, "#b33a3a"]
        bars = ax.bar(["Plain\nNL", "Plain\nplan", "Sealed\nplan", "Sealed\nNL"], vals, color=cols, width=0.7, edgecolor="#1a1a1a", lw=0.5)
        set_acc_axis(ax)
        ax.set_title(title, fontsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if ax is axes[0]:
            ax.set_ylabel("Exact accuracy")
        for b, t, v in zip(bars, texts, vals):
            label_bar(ax, b, t, v, fontsize=8)
    # Not included in main.tex / oir-arxiv.zip (scores are in appendix prose).
    fig.savefig(OUT / "fig5_realqa_2x2.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig5_realqa_2x2.png", dpi=200, bbox_inches="tight")
    plt.close()

    # Fig 7: opaque-rel dissociation + frozen n=200 non-LLM baselines
    opa = json.loads((RESULTS / "wiki_cf_opaque_rel_auto.json").read_text())["summary"]
    bench = json.loads((RESULTS / "oir_bench_baselines.json").read_text())
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.5), constrained_layout=True)

    ax = axes[0]
    labs = ["Plain\nNL", "Opaque-rel\nNL", "Sealed\nplan", "Legend\nNL"]
    keys = ["PLAIN_NL", "SPAN_NL", "SEAL_PROG", "LEGEND_NL"]
    texts = [opa[k]["score"] for k in keys]
    vals = [frac(t) for t in texts]
    cols = ["#2a6f6f", "#b33a3a", "#2a6f6f", "#2a6f6f"]
    bars = ax.bar(labs, vals, color=cols, width=0.7, edgecolor="#1a1a1a", lw=0.5)
    set_acc_axis(ax)
    ax.set_title("A. Opaque relations (Composer 2.5, n=12)", fontsize=10)
    ax.set_ylabel("Exact accuracy")
    for b, t, v in zip(bars, texts, vals):
        label_bar(ax, b, t, v, fontsize=8)

    ax = axes[1]
    w = bench["wiki_cf_n200"]
    labs = ["BM25\nplain", "BM25\nwiki leak", "SealRouter"]
    texts = [w["BM25_PLAIN"]["score"], w["BM25_PLAIN"]["wiki_leak"], w["SEALROUTER"]["score"]]
    vals = [frac(t) for t in texts]
    cols = ["#b33a3a", "#8a2020", "#2a6f6f"]
    bars = ax.bar(labs, vals, color=cols, width=0.7, edgecolor="#1a1a1a", lw=0.5)
    set_acc_axis(ax)
    ax.set_title("B. 2Wiki-CF n=200 (no LLM)", fontsize=10)
    for b, t, v in zip(bars, texts, vals):
        label_bar(ax, b, t, v, fontsize=8)

    ax = axes[2]
    s = bench["spider_n200"]
    labs = ["SQLite\noriginal", "Gold SQL\nengine", "BM25\nrow"]
    texts = [s["SQLITE_ORIG"]["score"], s["ENGINE_GOLD"]["score"], s["BM25_ROW"]["score"]]
    vals = [frac(t) for t in texts]
    cols = ["#2a6f6f", "#c47a2c", "#b33a3a"]
    bars = ax.bar(labs, vals, color=cols, width=0.7, edgecolor="#1a1a1a", lw=0.5)
    set_acc_axis(ax)
    ax.set_title("C. Spider JOIN n=200 (no LLM)", fontsize=10)
    for b, t, v in zip(bars, texts, vals):
        label_bar(ax, b, t, v, fontsize=8)

    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_yticks([0, 0.5, 1.0])
    fig.savefig(OUT / "fig7_opaque_rel_n200.pdf", bbox_inches="tight")
    fig.savefig(OUT / "fig7_opaque_rel_n200.png", dpi=200, bbox_inches="tight")
    plt.close()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
