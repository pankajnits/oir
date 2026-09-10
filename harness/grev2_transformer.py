#!/usr/bin/env python3
"""G-Rev2 v4 — tiny prompt-local Transformer (no HMAC vocab, no PATH-matched adjacency).

v3 numpy MP message-passes only along edges whose rel equals PATH R_k.
This net sees ALL triples as tokens plus an ordered PATH prefix; it must bind
PATH relation tokens to edges via attention.

Not G-Rev1: PATH + SINK_TYPE still given. Typed-decoy generator (type-only fails).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
from grev2_typed_sink import make_example, parse, typed_sink_router, unique_router  # noqa: E402
from grev2_local_mp import type_only  # noqa: E402

RESULTS = ROOT / "results"
SEED = 14
D = 32
NHEAD = 4
NLAYERS = 2
MAX_N = 28
MAX_E = 24
MAX_H = 4
EPOCHS = 12
BS = 32
LR = 3e-3
N_TRAIN = 2000
N_HOLD = 200
N_OOD = 100


def set_seed(s=SEED):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)


def local_ids(ex: dict):
    nodes = []
    rels = []
    for h, r, t in ex["triples"]:
        nodes.extend([h, t])
        rels.append(r)
    nodes = list(dict.fromkeys(nodes))
    rels = list(dict.fromkeys(rels))
    ni = {n: i for i, n in enumerate(nodes)}
    ri = {r: i for i, r in enumerate(rels)}
    typed = [0] * len(nodes)
    if ex["type_rel"] and ex["type_val"]:
        for h, r, t in ex["triples"]:
            if r == ex["type_rel"] and t == ex["type_val"] and h in ni:
                typed[ni[h]] = 1
    edges = [(ni[h], ri[r], ni[t]) for h, r, t in ex["triples"]]
    path_r = [ri[r] for r in ex["rels"] if r in ri]
    return {
        "nodes": nodes,
        "n": len(nodes),
        "e": len(edges),
        "nr": len(rels),
        "edges": edges,
        "path_r": path_r,
        "typed": typed,
        "start_i": ni.get(ex["start"], 0),
        "gold_i": ni.get(ex["gold"], 0),
        "gold": ex["gold"],
    }


def collate(batch: list[dict], oracle_path: bool):
    B = len(batch)
    # sequence: PATH hops + triples. Token = [kind, node_or_neg1, rel_or_neg1, hop_or_neg1]
    # We build per-item tensors padded.
    node_feat = torch.zeros(B, MAX_N, 3)  # start, typed, pad
    node_mask = torch.zeros(B, MAX_N, dtype=torch.bool)
    gold = torch.zeros(B, dtype=torch.long)
    n_nodes = torch.zeros(B, dtype=torch.long)

    # tokens: hop prefix (MAX_H) + edges (MAX_E)
    T = MAX_H + MAX_E
    tok_kind = torch.zeros(B, T, dtype=torch.long)  # 0 pad, 1 path, 2 edge
    tok_h = torch.zeros(B, T, dtype=torch.long)
    tok_r = torch.zeros(B, T, dtype=torch.long)
    tok_t = torch.zeros(B, T, dtype=torch.long)
    tok_hop = torch.zeros(B, T, dtype=torch.long)
    tok_pmatch = torch.zeros(B, T)  # oracle: 1 if edge rel is some PATH R_k
    tok_mask = torch.zeros(B, T, dtype=torch.bool)

    for b, g in enumerate(batch):
        n = min(g["n"], MAX_N)
        n_nodes[b] = n
        node_mask[b, :n] = True
        node_feat[b, g["start_i"] % MAX_N, 0] = 1.0
        for i, tv in enumerate(g["typed"][:n]):
            node_feat[b, i, 1] = float(tv)
        node_feat[b, :n, 2] = 1.0
        gold[b] = min(g["gold_i"], n - 1)
        path_set = set(g["path_r"])
        t = 0
        for k, r in enumerate(g["path_r"][:MAX_H]):
            tok_kind[b, t] = 1
            tok_r[b, t] = r + 1
            tok_hop[b, t] = k + 1
            tok_mask[b, t] = True
            t += 1
        t = MAX_H
        for h, r, tl in g["edges"][:MAX_E]:
            if h >= MAX_N or tl >= MAX_N:
                continue
            tok_kind[b, t] = 2
            tok_h[b, t] = h + 1
            tok_r[b, t] = r + 1
            tok_t[b, t] = tl + 1
            tok_mask[b, t] = True
            if oracle_path and r in path_set:
                tok_pmatch[b, t] = 1.0
            t += 1
    return {
        "node_feat": node_feat,
        "node_mask": node_mask,
        "gold": gold,
        "n_nodes": n_nodes,
        "tok_kind": tok_kind,
        "tok_h": tok_h,
        "tok_r": tok_r,
        "tok_t": tok_t,
        "tok_hop": tok_hop,
        "tok_pmatch": tok_pmatch,
        "tok_mask": tok_mask,
    }


class LocalTF(nn.Module):
    def __init__(self, d=D, oracle_path=False):
        super().__init__()
        self.oracle_path = oracle_path
        self.kind_emb = nn.Embedding(3, d)
        self.node_id = nn.Embedding(MAX_N + 1, d)
        self.rel_id = nn.Embedding(MAX_N + 1, d)
        self.hop_id = nn.Embedding(MAX_H + 1, d)
        self.nf = nn.Linear(3, d)
        self.pm = nn.Linear(1, d)
        enc_layer = nn.TransformerEncoderLayer(d_model=d, nhead=NHEAD, dim_feedforward=4 * d, batch_first=True, dropout=0.0)
        self.enc = nn.TransformerEncoder(enc_layer, num_layers=NLAYERS)
        self.node_q = nn.Linear(d, d)
        self.tok_k = nn.Linear(d, d)
        self.scorer = nn.Linear(d * 2, 1)

    def forward(self, b):
        B, T = b["tok_kind"].shape
        tok = (
            self.kind_emb(b["tok_kind"])
            + self.node_id(b["tok_h"])
            + self.rel_id(b["tok_r"])
            + self.node_id(b["tok_t"])
            + self.hop_id(b["tok_hop"])
        )
        if self.oracle_path:
            tok = tok + self.pm(b["tok_pmatch"].unsqueeze(-1))
        # pad tokens: mask True means KEEP in our tok_mask; transformer uses True=PAD
        pad = ~b["tok_mask"]
        h = self.enc(tok, src_key_padding_mask=pad)
        nf = self.nf(b["node_feat"])  # B, N, d
        # attend nodes to tokens
        q = self.node_q(nf)  # B, N, d
        k = self.tok_k(h)  # B, T, d
        attn = torch.matmul(q, k.transpose(1, 2)) / (D ** 0.5)  # B, N, T
        attn = attn.masked_fill(pad.unsqueeze(1), -1e9)
        w = torch.softmax(attn, dim=-1)
        ctx = torch.matmul(w, h)  # B, N, d
        logits = self.scorer(torch.cat([nf, ctx], dim=-1)).squeeze(-1)
        logits = logits.masked_fill(~b["node_mask"], -1e9)
        return logits


@torch.no_grad()
def acc(model, graphs, oracle_path, device):
    model.eval()
    k = 0
    for i in range(0, len(graphs), BS):
        chunk = graphs[i : i + BS]
        b = {kk: vv.to(device) for kk, vv in collate(chunk, oracle_path).items()}
        pred = model(b).argmax(-1)
        k += int((pred == b["gold"]).sum().item())
    return k, len(graphs)


def fit(model, train, hold, oracle_path, device, epochs=EPOCHS):
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    hist = []
    for ep in range(epochs):
        model.train()
        random.shuffle(train)
        losses = []
        for i in range(0, len(train), BS):
            chunk = train[i : i + BS]
            b = {kk: vv.to(device) for kk, vv in collate(chunk, oracle_path).items()}
            opt.zero_grad()
            logits = model(b)
            loss = F.cross_entropy(logits, b["gold"])
            loss.backward()
            opt.step()
            losses.append(float(loss.item()))
        tr_k, tr_n = acc(model, train[:400], oracle_path, device)
        ho_k, ho_n = acc(model, hold, oracle_path, device)
        rec = {"epoch": ep, "loss": float(np.mean(losses)), "train400": f"{tr_k}/{tr_n}", "holdout": f"{ho_k}/{ho_n}"}
        hist.append(rec)
        print(f"  ep {ep} loss={rec['loss']:.3f} train400={rec['train400']} hold={rec['holdout']}", flush=True)
    return hist


def pack_tf(model, graphs, oracle_path, device, raw):
    k, n = acc(model, graphs, oracle_path, device)
    ts = sum(typed_sink_router(ex) == ex["gold"] for ex in raw)
    uq = sum((unique_router(ex) or "") == ex["gold"] for ex in raw)
    to = sum(type_only(ex) == ex["gold"] for ex in raw)
    return {"tf": f"{k}/{n}", "typed_sink": f"{ts}/{n}", "unique": f"{uq}/{n}", "type_only": f"{to}/{n}", "n": n, "tf_k": k}


def main():
    set_seed()
    device = torch.device("cpu")
    rng = random.Random(SEED)
    train_raw = [parse(make_example(rng, i, hops=2, n_decoy=2, n_false_type=2, tag="trh")) for i in range(N_TRAIN)]
    hold_raw = [parse(make_example(rng, i, hops=2, n_decoy=2, n_false_type=2, tag="hoh")) for i in range(N_HOLD)]
    ood_raw = [parse(make_example(rng, i, hops=3, n_decoy=2, n_false_type=2, tag="ood3")) for i in range(N_OOD)]
    train = [local_ids(x) for x in train_raw]
    hold = [local_ids(x) for x in hold_raw]
    ood = [local_ids(x) for x in ood_raw]

    print("Transformer: no oracle path-match on edges")
    tf = LocalTF(oracle_path=False).to(device)
    hist = fit(tf, train, hold, False, device)

    print("Transformer: oracle path-match feature (MP-like hint)")
    tf_or = LocalTF(oracle_path=True).to(device)
    hist_or = fit(tf_or, train, hold, True, device)

    out = {
        "claim": (
            "Prompt-local Transformer, instance-fresh local ids, no HMAC lexicon. "
            "Default net is NOT given PATH-matched adjacency (unlike v3 MP). "
            "Oracle ablation adds a path-match bit on edges."
        ),
        "typed_decoy_holdout": pack_tf(tf, hold, False, device, hold_raw),
        "typed_decoy_holdout_oracle_pmatch": pack_tf(tf_or, hold, True, device, hold_raw),
        "typed_decoy_ood_h3": pack_tf(tf, ood, False, device, ood_raw),
        "typed_decoy_ood_h3_oracle_pmatch": pack_tf(tf_or, ood, True, device, ood_raw),
        "history": hist,
        "history_oracle": hist_or,
        "hparams": {"d": D, "nhead": NHEAD, "nlayers": NLAYERS, "epochs": EPOCHS, "n_train": N_TRAIN},
        "nonclaim": "PATH+SINK_TYPE given. Not G-Rev1. Tiny CPU Transformer, not a 1.5B SFT.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "grev2_transformer.json"
    path.write_text(json.dumps(out, indent=2))
    keys = (
        "typed_decoy_holdout",
        "typed_decoy_holdout_oracle_pmatch",
        "typed_decoy_ood_h3",
        "typed_decoy_ood_h3_oracle_pmatch",
    )
    print(json.dumps({k: out[k] for k in keys}, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
