#!/usr/bin/env python3
"""
G-Rev2 scaffold: tiny opaque Reasoner over sealed PATH.

Learns to map (PATH query + sealed CONTEXT) → final sealed atom.
This is a *neural* executor — not SealRouter script — toward G-Rev2.
G-Rev1 (no PATH) is out of scope here.

Default backend: pure NumPy bag-of-edges pointer (always runs).
Optional: PyTorch mini-Transformer if `torch` is importable (--torch).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "synthetic"
RESULTS = ROOT / "results"
PAPER = ROOT / "paper"

SEAL_RE = re.compile(r"E[0-9a-f]+")
TRIPLE_RE = re.compile(
    r"(E[0-9a-f]+)\s*\|\s*(E[0-9a-f]+)\s*\|\s*(E[0-9a-f]+)"
)


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def parse_example(ex: dict):
    text = ex["input"]
    gold = ex["output"].strip()
    start_m = re.search(r"START\s+(E[0-9a-f]+)", text)
    rels = re.findall(r"R\d+\s+(E[0-9a-f]+)", text)
    triples = TRIPLE_RE.findall(text)
    start = start_m.group(1) if start_m else None
    return {
        "start": start,
        "rels": rels,
        "triples": [(h, r, t) for h, r, t in triples],
        "gold": gold,
        "raw": ex,
    }


def seal_router_path(start: str, rels: list[str], triples: list[tuple[str, str, str]]):
    """Exact symbolic ceiling (SealRouter-equivalent)."""
    adj = defaultdict(list)
    for h, r, t in triples:
        adj[(h, r)].append(t)
    cur = start
    for r in rels:
        outs = adj.get((cur, r), [])
        if not outs:
            return None
        # deterministic: first unique
        cur = list(dict.fromkeys(outs))[0]
    return cur


# ---- NumPy / pure-Python learned Reasoner: relation-keyed hop embedding ----
# Model: for each training path, memorize (rel_seq fingerprint -> next) is wrong for OOD.
# Instead: learn P(tail | head, rel) as MLE from training edges, then execute PATH.
# This is a *statistical* Reasoner (counts), not a script with hardcoded HMAC —
# honest G-Rev2 *floor*: learned edge table. Stronger neural follows if torch present.


class CountReasoner:
    def __init__(self):
        self.edge_count: dict[tuple[str, str], Counter] = defaultdict(Counter)
        self.n_edges = 0

    def fit(self, examples: list[dict]):
        for ex in examples:
            for h, r, t in ex["triples"]:
                self.edge_count[(h, r)][t] += 1
                self.n_edges += 1

    def step(self, h: str, r: str) -> str | None:
        c = self.edge_count.get((h, r))
        if not c:
            return None
        return c.most_common(1)[0][0]

    def predict(self, ex: dict) -> str | None:
        cur = ex["start"]
        if cur is None:
            return None
        for r in ex["rels"]:
            nxt = self.step(cur, r)
            if nxt is None:
                return None
            cur = nxt
        return cur


class InstanceLocalReasoner:
    """
    True opaque executor for G-Rev2 eval: for each *instance*, build edge index
    from that instance's CONTEXT only, then walk PATH — learned policy is
    'index then hop', identical in form to SealRouter but implemented as a
    trainable-style procedure we can replace with a neural net.
    Used as behavioral upper bound matching SealRouter on in-prompt edges.
    """

    def predict(self, ex: dict) -> str | None:
        return seal_router_path(ex["start"], ex["rels"], ex["triples"])


def try_torch_train(train, holdout, epochs: int, seed: int):
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError:
        return None

    # CPU: TransformerEncoder+pad mask is unreliable on MPS (nested_tensor op).
    device = torch.device("cpu")
    rng = random.Random(seed)

    # Vocab from train only for input ids; holdout seals → <unk> unless overlap
    seals = set()
    for ex in train:
        seals.update(SEAL_RE.findall(ex["raw"]["input"]))
        seals.add(ex["gold"])
    specials = ["<pad>", "<unk>", "<start>", "<rsep>", "<ctx>"]
    itos = specials + sorted(seals)
    stoi = {t: i for i, t in enumerate(itos)}
    V = len(itos)
    pad = stoi["<pad>"]
    unk = stoi["<unk>"]

    def encode_ex(ex, max_len=96):
        toks = [stoi["<start>"], stoi.get(ex["start"], unk)]
        for r in ex["rels"]:
            toks += [stoi["<rsep>"], stoi.get(r, unk)]
        toks.append(stoi["<ctx>"])
        for h, r, t in ex["triples"][:16]:
            toks += [stoi.get(h, unk), stoi.get(r, unk), stoi.get(t, unk)]
        toks = toks[: max_len - 1]
        y = stoi.get(ex["gold"], unk)
        x = toks + [pad] * (max_len - len(toks))
        return x, y

    class TinyExec(nn.Module):
        """Mean-pool MLP over token embeddings — MPS/CPU safe; prompt-local via embeddings."""

        def __init__(self, v, d=96):
            super().__init__()
            self.emb = nn.Embedding(v, d, padding_idx=pad)
            self.mlp = nn.Sequential(
                nn.Linear(d, 192),
                nn.ReLU(),
                nn.Linear(192, 192),
                nn.ReLU(),
                nn.Linear(192, v),
            )

        def forward(self, x):
            h = self.emb(x)
            mask = (x != pad).unsqueeze(-1).float()
            pooled = (h * mask).sum(1) / mask.sum(1).clamp(min=1.0)
            return self.mlp(pooled)

    model = TinyExec(V).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3)
    Xy = [encode_ex(ex) for ex in train]
    hold_Xy = [encode_ex(ex) for ex in holdout]

    def run_epoch(pairs, train_mode=True):
        model.train(train_mode)
        total_loss, correct, n = 0.0, 0, 0
        idxs = list(range(len(pairs)))
        if train_mode:
            rng.shuffle(idxs)
        bs = 64
        ctx = torch.enable_grad() if train_mode else torch.no_grad()
        with ctx:
            for i0 in range(0, len(idxs), bs):
                batch = [pairs[i] for i in idxs[i0 : i0 + bs]]
                xb = torch.tensor([x for x, _ in batch], device=device)
                yb = torch.tensor([y for _, y in batch], device=device)
                logits = model(xb)
                loss = F.cross_entropy(logits, yb)
                if train_mode:
                    opt.zero_grad()
                    loss.backward()
                    opt.step()
                total_loss += float(loss.item()) * len(batch)
                pred = logits.argmax(-1)
                correct += int((pred == yb).sum().item())
                n += len(batch)
        return total_loss / max(n, 1), correct / max(n, 1)

    hist = []
    for ep in range(epochs):
        tr_loss, tr_acc = run_epoch(Xy, True)
        va_loss, va_acc = run_epoch(hold_Xy, False)
        hist.append(
            {"epoch": ep, "train_acc": tr_acc, "holdout_acc": va_acc, "train_loss": tr_loss}
        )
        if ep % max(1, epochs // 5) == 0 or ep == epochs - 1:
            print(f"  torch ep {ep}: train_acc={tr_acc:.3f} holdout_acc={va_acc:.3f}")

    ckpt = RESULTS / "tiny_reasoner_torch.pt"
    torch.save({"model": model.state_dict(), "stoi": stoi, "itos": itos}, ckpt)
    return {
        "backend": "torch_meanpool_mlp",
        "device": str(device),
        "vocab": V,
        "epochs": epochs,
        "history": hist,
        "holdout_acc": hist[-1]["holdout_acc"] if hist else None,
        "train_acc": hist[-1]["train_acc"] if hist else None,
        "ckpt": str(ckpt),
        "note": (
            "Holdout seals are mostly <unk> under train-only vocab — low holdout acc expected "
            "unless the net invents prompt-local walks. High train + low holdout = lexicon fail."
        ),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--torch", action="store_true", help="Try PyTorch TinyExec if available")
    ap.add_argument("--max-train", type=int, default=4800)
    args = ap.parse_args()

    train_raw = load_jsonl(DATA / "sealed_path_train.jsonl")[: args.max_train]
    hold_raw = load_jsonl(DATA / "sealed_path_holdout.jsonl")
    train = [parse_example(x) for x in train_raw]
    hold = [parse_example(x) for x in hold_raw]

    # Ceiling: instance-local exact walk
    local = InstanceLocalReasoner()
    local_ok = sum(1 for ex in hold if local.predict(ex) == ex["gold"])

    # Count reasoner: WRONG for holdout if seals are instance-fresh (expected fail)
    counts = CountReasoner()
    counts.fit(train)
    count_ok = sum(1 for ex in hold if counts.predict(ex) == ex["gold"])

    # Global count on holdout edges only (oracle leak) — shows task is solvable by indexing
    hold_counts = CountReasoner()
    hold_counts.fit(hold)
    hold_count_ok = sum(1 for ex in hold if hold_counts.predict(ex) == ex["gold"])

    out = {
        "claim": (
            "G-Rev2 scaffold: neural/count Reasoner vs instance-local executor (SealRouter-equivalent). "
            "Instance-local walk is the opaque executor ceiling; global count fails on fresh seals."
        ),
        "n_train": len(train),
        "n_holdout": len(hold),
        "instance_local_holdout": f"{local_ok}/{len(hold)}",
        "global_count_holdout": f"{count_ok}/{len(hold)}",
        "holdout_fit_count_oracle": f"{hold_count_ok}/{len(hold)}",
        "reading": (
            "Fresh seals per instance → memorizing train edges cannot transfer (global_count≈0). "
            "Instance-local indexing recovers PATH (ceiling). G-Rev2 needs a Reasoner that "
            "binds *within* the prompt graph, not a lexicon of seals — next: torch TinyExec "
            "or SFT Qwen on (input→output) with prompt-local attention."
        ),
        "torch": None,
        "seed": args.seed,
        "ts": time.time(),
    }

    print("instance_local", out["instance_local_holdout"])
    print("global_count  ", out["global_count_holdout"], "(expect near 0 if seals fresh)")
    print("hold_oracle   ", out["holdout_fit_count_oracle"])

    if args.torch:
        print("training torch TinyExec...")
        out["torch"] = try_torch_train(train, hold, args.epochs, args.seed)
        if out["torch"] is None:
            print("torch not installed — skip neural train")
        else:
            print("torch holdout_acc", out["torch"].get("holdout_acc"))

    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "tiny_reasoner_g_rev2.json"
    path.write_text(json.dumps(out, indent=2))
    print("wrote", path)

    # paper note
    note = PAPER / "G_REV2_REASONER.md"
    torch_line = (
        f"Torch TinyExec holdout acc: **{out['torch'].get('holdout_acc'):.3f}** "
        f"({out['torch'].get('device')})."
        if out.get("torch") and out["torch"].get("holdout_acc") is not None
        else "Torch train not run (install torch + `--torch`)."
    )
    note.write_text(
        f"""# G-Rev2 — Tiny Opaque Reasoner (scaffold lock)

Date: 2026-08-03  
Status: **SCAFFOLD LOCK** — existence of the right eval; neural SFT optional  
Data: `data/synthetic/sealed_path_{{train,holdout}}.jsonl`

## Question
Can a **learned** executor answer sealed PATH queries without being a hand-written
SealRouter script — and without relying on a global seal lexicon?

## Results (this run)

| Executor | Holdout |
|----------|---------|
| Instance-local walk (SealRouter-equivalent) | **{out['instance_local_holdout']}** |
| Global count Reasoner (fit train edges) | **{out['global_count_holdout']}** |
| Count fit on holdout edges (oracle leak) | **{out['holdout_fit_count_oracle']}** |

{torch_line}

## Locked reading
1. Seals are **instance-fresh** → memorizing training edges does not transfer.
2. Opaque execution requires **prompt-local** binding (index CONTEXT, walk PATH).
3. SealRouter is the exact ceiling for gold PATH; G-Rev2 is a *learned* policy with
   the same interface — not G-Rev1 (still needs PATH).
4. Next train: SFT small LM on jsonl (`tiny_reasoner_train_plan.json`) so attention
   implements the walk; eval rename + trap quizzes.

## Non-claims
- Not G-Rev1 solved
- Not that count models are the Reasoner destination
- Not product routing

## Artifacts
- `harness/tiny_reasoner_train.py`
- `results/tiny_reasoner_g_rev2.json`
- `results/tiny_reasoner_train_plan.json`
"""
    )
    print("wrote", note)


if __name__ == "__main__":
    main()
