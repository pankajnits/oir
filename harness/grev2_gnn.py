#!/usr/bin/env python3
"""G-Rev2 v4b — torch MP (hard PATH edges) vs soft-rel GNN (must bind PATH rels).

The sequence Transformer collapsed to ln(3) (~3 last-hop candidates). This file
asks whether that is encoding failure or whether neural executors need a hard
PATH adjacency filter.

  TorchMP: message-pass ONLY along PATH-matched edges + type bit (v3 in autograd).
  SoftRelGNN: message-pass on ALL edges gated by sigmoid(rel·path_k); type bit.

Not G-Rev1. Typed-decoy generator.
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
D = 16
MAX_N = 28
MAX_E = 24
MAX_H = 4
EPOCHS = 10
BS = 32
LR = 5e-3
N_TRAIN = 2000
N_HOLD = 200
N_OOD = 100


def set_seed(s=SEED):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)


def pack_ex(ex: dict) -> dict:
    nodes = []
    rels_all = []
    for h, r, t in ex["triples"]:
        nodes.extend([h, t])
        rels_all.append(r)
    nodes = list(dict.fromkeys(nodes))
    rels_all = list(dict.fromkeys(rels_all))
    ni = {n: i for i, n in enumerate(nodes)}
    ri = {r: i for i, r in enumerate(rels_all)}
    typed = [0.0] * len(nodes)
    if ex["type_rel"] and ex["type_val"]:
        for h, r, t in ex["triples"]:
            if r == ex["type_rel"] and t == ex["type_val"] and h in ni:
                typed[ni[h]] = 1.0
    edges = [(ni[h], ri[r], ni[t]) for h, r, t in ex["triples"]]
    path_r = [ri[r] for r in ex["rels"] if r in ri]
    hop_edges = []
    for rq in ex["rels"]:
        hop_edges.append([(ni[h], ni[t]) for h, r, t in ex["triples"] if r == rq and h in ni and t in ni])
    return {
        "n": len(nodes),
        "nodes": nodes,
        "nr": len(rels_all),
        "edges": edges,
        "path_r": path_r,
        "hop_edges": hop_edges,
        "typed": typed,
        "start_i": ni.get(ex["start"], 0),
        "gold_i": ni.get(ex["gold"], 0),
        "gold": ex["gold"],
    }


def collate(batch, hard: bool):
    B = len(batch)
    start = torch.zeros(B, dtype=torch.long)
    gold = torch.zeros(B, dtype=torch.long)
    n_nodes = torch.zeros(B, dtype=torch.long)
    typed = torch.zeros(B, MAX_N)
    node_mask = torch.zeros(B, MAX_N, dtype=torch.bool)
    # edges padded
    eh = torch.zeros(B, MAX_E, dtype=torch.long)
    er = torch.zeros(B, MAX_E, dtype=torch.long)
    et = torch.zeros(B, MAX_E, dtype=torch.long)
    emask = torch.zeros(B, MAX_E, dtype=torch.bool)
    path = torch.zeros(B, MAX_H, dtype=torch.long)
    pmask = torch.zeros(B, MAX_H, dtype=torch.bool)
    # hard hop edges: MAX_H x MAX_E
    hh = torch.zeros(B, MAX_H, MAX_E, dtype=torch.long)
    ht = torch.zeros(B, MAX_H, MAX_E, dtype=torch.long)
    hm = torch.zeros(B, MAX_H, MAX_E, dtype=torch.bool)

    for b, g in enumerate(batch):
        n = min(g["n"], MAX_N)
        n_nodes[b] = n
        node_mask[b, :n] = True
        start[b] = min(g["start_i"], n - 1)
        gold[b] = min(g["gold_i"], n - 1)
        for i, tv in enumerate(g["typed"][:n]):
            typed[b, i] = tv
        for i, r in enumerate(g["path_r"][:MAX_H]):
            path[b, i] = r
            pmask[b, i] = True
        for i, (h, r, t) in enumerate(g["edges"][:MAX_E]):
            if h >= MAX_N or t >= MAX_N:
                continue
            eh[b, i], er[b, i], et[b, i] = h, r, t
            emask[b, i] = True
        for k, edges in enumerate(g["hop_edges"][:MAX_H]):
            for i, (h, t) in enumerate(edges[:MAX_E]):
                if h >= MAX_N or t >= MAX_N:
                    continue
                hh[b, k, i], ht[b, k, i] = h, t
                hm[b, k, i] = True
    return {
        "start": start,
        "gold": gold,
        "n_nodes": n_nodes,
        "typed": typed,
        "node_mask": node_mask,
        "eh": eh,
        "er": er,
        "et": et,
        "emask": emask,
        "path": path,
        "pmask": pmask,
        "hh": hh,
        "ht": ht,
        "hm": hm,
    }


class TorchMP(nn.Module):
    """Hard PATH-matched MP + type bit (v3 with full BPTT)."""

    def __init__(self):
        super().__init__()
        self.e_start = nn.Parameter(torch.randn(D) * 0.1)
        self.e_other = nn.Parameter(torch.randn(D) * 0.1)
        self.W = nn.Parameter(torch.randn(MAX_H, D, D) * 0.1)
        self.w = nn.Parameter(torch.randn(D) * 0.1)
        self.b_type = nn.Parameter(torch.zeros(1))

    def forward(self, b):
        B = b["start"].shape[0]
        H = self.e_other.view(1, 1, D).expand(B, MAX_N, D).clone()
        idx = b["start"].view(B, 1, 1).expand(B, 1, D)
        H.scatter_(1, idx, self.e_start.view(1, 1, D).expand(B, 1, D))
        for k in range(MAX_H):
            src = H.gather(1, b["hh"][:, k].unsqueeze(-1).expand(B, MAX_E, D))
            msg = torch.matmul(src, self.W[k])  # B, E, D
            msg = msg * b["hm"][:, k].unsqueeze(-1)
            H2 = torch.zeros_like(H)
            H2.scatter_add_(1, b["ht"][:, k].unsqueeze(-1).expand(B, MAX_E, D), msg)
            # only update if this hop has any edges
            has = b["hm"][:, k].any(-1).view(B, 1, 1)
            H = torch.where(has, torch.tanh(H2), H)
        logits = H @ self.w + self.b_type * b["typed"]
        logits = logits.masked_fill(~b["node_mask"], -1e9)
        return logits


class SoftRelGNN(nn.Module):
    """All edges; gate = sigmoid(rel_emb · path_k_emb). Must learn PATH binding."""

    def __init__(self):
        super().__init__()
        self.e_start = nn.Parameter(torch.randn(D) * 0.1)
        self.e_other = nn.Parameter(torch.randn(D) * 0.1)
        self.rel = nn.Embedding(MAX_N, D)
        self.W = nn.Parameter(torch.randn(MAX_H, D, D) * 0.1)
        self.w = nn.Parameter(torch.randn(D) * 0.1)
        self.b_type = nn.Parameter(torch.zeros(1))

    def forward(self, b):
        B = b["start"].shape[0]
        H = self.e_other.view(1, 1, D).expand(B, MAX_N, D).clone()
        idx = b["start"].view(B, 1, 1).expand(B, 1, D)
        H.scatter_(1, idx, self.e_start.view(1, 1, D).expand(B, 1, D))
        er = self.rel(b["er"].clamp(max=MAX_N - 1))  # B, E, D
        for k in range(MAX_H):
            pr = self.rel(b["path"][:, k].clamp(max=MAX_N - 1))  # B, D
            gate = torch.sigmoid((er * pr.unsqueeze(1)).sum(-1) / (D ** 0.5))  # B, E
            gate = gate * b["emask"] * b["pmask"][:, k].unsqueeze(1)
            src = H.gather(1, b["eh"].unsqueeze(-1).expand(B, MAX_E, D))
            msg = torch.matmul(src, self.W[k]) * gate.unsqueeze(-1)
            H2 = torch.zeros_like(H)
            H2.scatter_add_(1, b["et"].unsqueeze(-1).expand(B, MAX_E, D), msg)
            has = b["pmask"][:, k].view(B, 1, 1)
            H = torch.where(has, torch.tanh(H2), H)
        logits = H @ self.w + self.b_type * b["typed"]
        logits = logits.masked_fill(~b["node_mask"], -1e9)
        return logits


@torch.no_grad()
def acc(model, graphs, hard, device):
    model.eval()
    k = 0
    for i in range(0, len(graphs), BS):
        b = {kk: vv.to(device) for kk, vv in collate(graphs[i : i + BS], hard).items()}
        pred = model(b).argmax(-1)
        k += int((pred == b["gold"]).sum().item())
    return k, len(graphs)


def fit(model, train, hold, hard, device, name):
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    hist = []
    print(name)
    for ep in range(EPOCHS):
        model.train()
        random.shuffle(train)
        losses = []
        for i in range(0, len(train), BS):
            b = {kk: vv.to(device) for kk, vv in collate(train[i : i + BS], hard).items()}
            opt.zero_grad()
            loss = F.cross_entropy(model(b), b["gold"])
            loss.backward()
            opt.step()
            losses.append(float(loss.item()))
        tr = acc(model, train[:400], hard, device)
        ho = acc(model, hold, hard, device)
        rec = {"epoch": ep, "loss": float(np.mean(losses)), "train400": f"{tr[0]}/{tr[1]}", "holdout": f"{ho[0]}/{ho[1]}"}
        hist.append(rec)
        print(f"  ep {ep} loss={rec['loss']:.3f} train400={rec['train400']} hold={rec['holdout']}", flush=True)
    return hist


def pack(model, graphs, raw, hard, device):
    k, n = acc(model, graphs, hard, device)
    ts = sum(typed_sink_router(ex) == ex["gold"] for ex in raw)
    uq = sum((unique_router(ex) or "") == ex["gold"] for ex in raw)
    to = sum(type_only(ex) == ex["gold"] for ex in raw)
    return {"nn": f"{k}/{n}", "typed_sink": f"{ts}/{n}", "unique": f"{uq}/{n}", "type_only": f"{to}/{n}", "n": n, "nn_k": k}


def main():
    set_seed()
    device = torch.device("cpu")
    rng = random.Random(SEED)
    train_raw = [parse(make_example(rng, i, hops=2, n_decoy=2, n_false_type=2, tag="trh")) for i in range(N_TRAIN)]
    hold_raw = [parse(make_example(rng, i, hops=2, n_decoy=2, n_false_type=2, tag="hoh")) for i in range(N_HOLD)]
    ood_raw = [parse(make_example(rng, i, hops=3, n_decoy=2, n_false_type=2, tag="ood3")) for i in range(N_OOD)]
    train = [pack_ex(x) for x in train_raw]
    hold = [pack_ex(x) for x in hold_raw]
    ood = [pack_ex(x) for x in ood_raw]

    mp = TorchMP().to(device)
    hist_mp = fit(mp, train, hold, True, device, "TorchMP hard PATH edges")

    gnn = SoftRelGNN().to(device)
    hist_g = fit(gnn, train, hold, False, device, "SoftRelGNN (learn PATH binding)")

    def strip_path(g):
        h = dict(g)
        h["path_r"] = []
        h["hop_edges"] = [[] for _ in g["hop_edges"]]
        return h

    def strip_type(g):
        h = dict(g)
        h["typed"] = [0.0] * g["n"]
        return h

    hold_nopath = [strip_path(g) for g in hold]
    hold_notype = [strip_type(g) for g in hold]
    k_np, n_np = acc(gnn, hold_nopath, False, device)
    k_nt, n_nt = acc(gnn, hold_notype, False, device)

    gnn_np = SoftRelGNN().to(device)
    train_np = [strip_path(g) for g in train]
    hist_np = fit(gnn_np, train_np, hold_nopath, False, device, "SoftRelGNN TRAIN without PATH")
    k_np_tr, n_np_tr = acc(gnn_np, hold_nopath, False, device)

    out = {
        "claim": (
            "Autograd MP with hard PATH adjacency vs GNN that must bind PATH rel embeddings. "
            "Sequence Transformer (grev2_transformer.py) collapsed to ln(3). "
            "Ablations: test-time PATH drop / type drop; train without PATH (not G-Rev1)."
        ),
        "torch_mp_holdout": pack(mp, hold, hold_raw, True, device),
        "soft_gnn_holdout": pack(gnn, hold, hold_raw, False, device),
        "torch_mp_ood_h3": pack(mp, ood, ood_raw, True, device),
        "soft_gnn_ood_h3": pack(gnn, ood, ood_raw, False, device),
        "gnn_test_drop_path": f"{k_np}/{n_np}",
        "gnn_test_drop_type": f"{k_nt}/{n_nt}",
        "gnn_train_no_path": f"{k_np_tr}/{n_np_tr}",
        "history_mp": hist_mp,
        "history_gnn": hist_g,
        "history_gnn_no_path": hist_np,
        "transformer_holdout": "101/200 (ln3 collapse; see grev2_transformer.json)",
        "nonclaim": "PATH+SINK_TYPE given. Not G-Rev1. Tiny CPU nets, not 1.5B SFT.",
    }
    path = RESULTS / "grev2_gnn.json"
    path.write_text(json.dumps(out, indent=2))
    keys = ("torch_mp_holdout", "soft_gnn_holdout", "torch_mp_ood_h3", "soft_gnn_ood_h3")
    print(json.dumps({k: out[k] for k in keys}, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
