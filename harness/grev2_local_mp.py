#!/usr/bin/env python3
"""G-Rev2 v3 — prompt-local message passing without hand-coded reachability.

Seals are instance-fresh, so a global vocab MLP cannot transfer.
This executor:
  * remaps seals to local node ids per prompt (no HMAC lexicon)
  * message-passes only along edges whose relation token equals PATH R_k
  * scores nodes with a learned vector (plus a type-edge bias learned, not DFS)

Compare to typed-sink router (symbolic ceiling) and unique-edge SealRouter.
Not G-Rev1: PATH + SINK_TYPE still given.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from grev2_typed_sink import make_example, parse, typed_sink_router, unique_router  # noqa: E402

DATA = ROOT / "data" / "synthetic"
RESULTS = ROOT / "results"
D = 12
LR = 0.05
EPOCHS = 8
SEED = 7


def load_jsonl(path: Path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def local_graph(ex: dict):
    nodes = []
    for h, r, t in ex["triples"]:
        nodes.extend([h, t])
    nodes = list(dict.fromkeys(nodes))
    idx = {n: i for i, n in enumerate(nodes)}
    rel_edges = {}
    for h, r, t in ex["triples"]:
        rel_edges.setdefault(r, []).append((idx[h], idx[t]))
    typed = np.zeros(len(nodes), dtype=np.float64)
    if ex["type_rel"] and ex["type_val"]:
        for h, r, t in ex["triples"]:
            if r == ex["type_rel"] and t == ex["type_val"] and h in idx:
                typed[idx[h]] = 1.0
    gold_i = idx.get(ex["gold"])
    start_i = idx.get(ex["start"])
    hop_edges = [rel_edges.get(rq, []) for rq in ex["rels"]]
    return {
        "n": len(nodes),
        "idx": idx,
        "nodes": nodes,
        "hop_edges": hop_edges,
        "typed": typed,
        "gold_i": gold_i,
        "start_i": start_i,
    }


def type_only(ex: dict) -> str | None:
    """Pick a node with the SINK_TYPE edge. Unique on v2 generator; not unique with false types."""
    hits = [h for h, r, t in ex["triples"] if r == ex["type_rel"] and t == ex["type_val"]]
    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None


class LocalMP:
    """Tiny prompt-local MP: h <- W_k h along PATH-matched edges; score = h·w + b_type * typed."""

    def __init__(self, d=D, seed=SEED, use_type: bool = True):
        rng = np.random.default_rng(seed)
        self.d = d
        self.use_type = use_type
        self.e_start = rng.normal(0, 0.1, d)
        self.e_other = rng.normal(0, 0.1, d)
        self.W = [rng.normal(0, 0.1, (d, d)) for _ in range(4)]
        self.w = rng.normal(0, 0.1, d)
        self.b_type = 0.0

    def forward(self, g: dict):
        n, d = g["n"], self.d
        H = np.tile(self.e_other, (n, 1))
        if g["start_i"] is not None:
            H[g["start_i"]] = self.e_start
        for k, edges in enumerate(g["hop_edges"]):
            W = self.W[min(k, len(self.W) - 1)]
            H2 = np.zeros_like(H)
            for s, t in edges:
                H2[t] += W @ H[s]
            H = np.tanh(H2) if edges else H
        typed = g["typed"] if self.use_type else np.zeros(n)
        logits = H @ self.w + self.b_type * typed
        return logits, H

    def predict_seal(self, ex: dict) -> str | None:
        g = local_graph(ex)
        if g["n"] == 0:
            return None
        logits, _ = self.forward(g)
        return g["nodes"][int(np.argmax(logits))]

    def train_step(self, g: dict):
        if g["gold_i"] is None:
            return 0.0
        logits, H = self.forward(g)
        m = np.max(logits)
        exp = np.exp(logits - m)
        p = exp / exp.sum()
        loss = -np.log(p[g["gold_i"]] + 1e-12)
        dlog = p.copy()
        dlog[g["gold_i"]] -= 1.0
        self.w -= LR * (H.T @ dlog)
        typed = g["typed"] if self.use_type else np.zeros(g["n"])
        self.b_type -= LR * float(dlog @ typed)
        dH = np.outer(dlog, self.w)
        k_last = min(len(g["hop_edges"]) - 1, len(self.W) - 1)
        if k_last >= 0 and g["hop_edges"][k_last]:
            H_prev = np.tile(self.e_other, (g["n"], 1))
            if g["start_i"] is not None:
                H_prev[g["start_i"]] = self.e_start
            dW = np.zeros_like(self.W[k_last])
            d_start = np.zeros(self.d)
            d_other = np.zeros(self.d)
            for s, t in g["hop_edges"][k_last]:
                dW += np.outer(dH[t], H_prev[s])
                if s == g["start_i"]:
                    d_start += self.W[k_last].T @ dH[t]
                else:
                    d_other += self.W[k_last].T @ dH[t]
            self.W[k_last] -= LR * dW
            self.e_start -= LR * d_start
            self.e_other -= LR * d_other
        return float(loss)


def acc(model: LocalMP, rows: list[dict]) -> tuple[int, int]:
    k = 0
    for r in rows:
        ex = r if "triples" in r else parse(r)
        k += int(model.predict_seal(ex) == ex["gold"])
    return k, len(rows)


def type_only_acc(rows: list[dict]) -> tuple[int, int]:
    k = 0
    for r in rows:
        ex = r if "triples" in r else parse(r)
        k += int(type_only(ex) == ex["gold"])
    return k, len(rows)


def fit(model: LocalMP, train: list[dict], hold: list[dict], epochs: int, rng: random.Random):
    graphs = [local_graph(ex) for ex in train]
    hist = []
    for ep in range(epochs):
        rng.shuffle(graphs)
        losses = [model.train_step(g) for g in graphs]
        tr_k, tr_n = acc(model, train[:400])
        ho_k, ho_n = acc(model, hold)
        hist.append({"epoch": ep, "loss": float(np.mean(losses)), "train400": f"{tr_k}/{tr_n}", "holdout": f"{ho_k}/{ho_n}"})
        print(f"  ep {ep} loss={hist[-1]['loss']:.3f} train400={hist[-1]['train400']} hold={hist[-1]['holdout']}")
    return hist


def pack(model: LocalMP, rows: list[dict]) -> dict:
    k, n = acc(model, rows)
    ts = sum(typed_sink_router(ex) == ex["gold"] for ex in rows)
    uq = sum((unique_router(ex) or "") == ex["gold"] for ex in rows)
    to_k, _ = type_only_acc(rows)
    return {
        "mp": f"{k}/{n}",
        "typed_sink": f"{ts}/{n}",
        "unique": f"{uq}/{n}",
        "type_only": f"{to_k}/{n}",
        "n": n,
        "mp_k": k,
        "type_only_k": to_k,
    }


def main():
    rng = random.Random(SEED)
    hold_v2 = [parse(x) for x in load_jsonl(DATA / "grev2_typed_sink_holdout.jsonl")]
    train_hard = [parse(make_example(rng, i, hops=2, n_decoy=2, n_false_type=2, tag="trh")) for i in range(2000)]
    hold_hard = [parse(make_example(rng, i, hops=2, n_decoy=2, n_false_type=2, tag="hoh")) for i in range(200)]
    ood_h3 = [parse(make_example(rng, i, hops=3, n_decoy=2, n_false_type=2, tag="ood3")) for i in range(100)]

    print("MP + type bias on typed-decoy generator")
    mp = LocalMP(use_type=True)
    hist = fit(mp, train_hard, hold_hard, EPOCHS, rng)

    print("MP no type bias")
    mp_not = LocalMP(use_type=False, seed=SEED + 1)
    hist_not = fit(mp_not, train_hard, hold_hard, EPOCHS, rng)

    out = {
        "claim": (
            "Prompt-local MP without can_reach DFS. v2 holdout is type-unique (type-only saturates). "
            "Typed-decoy generator: false typed nodes off-path, so type-only fails; walker+type required."
        ),
        "v2_holdout_type_unique": pack(mp, hold_v2),
        "typed_decoy_holdout": pack(mp, hold_hard),
        "typed_decoy_holdout_mp_no_type": pack(mp_not, hold_hard),
        "typed_decoy_ood_h3": pack(mp, ood_h3),
        "history_mp": hist,
        "history_mp_no_type": hist_not,
        "nonclaim": "PATH+SINK_TYPE given. Not G-Rev1. Not a Transformer SFT.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "grev2_local_mp.json"
    path.write_text(json.dumps(out, indent=2))
    keys = ("v2_holdout_type_unique", "typed_decoy_holdout", "typed_decoy_holdout_mp_no_type", "typed_decoy_ood_h3")
    print(json.dumps({k: out[k] for k in keys}, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
