# OIR — Opaque Isomorphic Reasoning

[![CI](https://github.com/pankajnits/oir/actions/workflows/ci.yml/badge.svg)](https://github.com/pankajnits/oir/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Measurement protocol and HMAC middle layer for the paper
*When Can Language Models Join Without Lexical Cues?*

**Code, isolation quizzes (`runs/`), and locked scores (`results/`):**
[github.com/pankajnits/oir](https://github.com/pankajnits/oir)

**PDF (NeurIPS preprint, 9 content pages + appendix):**
[`paper/arxiv_upload/main.pdf`](paper/arxiv_upload/main.pdf)

Cite this repository with [`CITATION.cff`](CITATION.cff).

```bash
git clone https://github.com/pankajnits/oir.git
cd oir
pip install -e '.[dev]'
python3 -m pytest tests/ -q
```

From a checkout you can also `pip install git+https://github.com/pankajnits/oir.git`. The import name is `oir`; the PyPI-style distribution name is `oir-layer`.

Compile the paper: `cd paper/arxiv_upload && tectonic -X compile main.tex`
(see [`paper/README.md`](paper/README.md)). arXiv upload is
[`paper/oir-arxiv.zip`](paper/oir-arxiv.zip) (**no** PDF inside).

HMAC seals are an **instrument** (instance-wise injective renaming that preserves equality). They are not confidentiality, HIPAA, or IND-CPA. Missing cells are `n.r.`, never zeros.

## Headline (Composer 2.5, OpenAI `gpt-5.6-sol`, Grok 4.5)

| Cell | Result |
|------|--------|
| Unique path, both-opaque (entities+relations sealed) | **32/32** all three families |
| Unique path, relation-opaque Wikidata 2×2 | OpenAI **32/32**; Composer **27/32**; Grok **30/32** |
| English Wikidata 2×2 (OpenAI; relations readable) | unique **31/32**, two-path **31/32** |
| Opacity × two same-type paths (OpenAI Wikidata 2×2) | English two-path **31/32** → opaque **6/32** (UNK 24, decoy 2; McNemar 25 vs 0) |
| Same graphs, Composer / Grok two-path | Composer English **26/32** → opaque **10/32**; Grok English **4/32** (UNK 28) → opaque **1/32** |
| WikiMovies Condition A n=100 (OpenAI) | two-path **96/100**; on 32 names shared with A32, **29/32** (A32 was **17/32**) |
| WikiMovies Condition B n=100 (OpenAI) | unique **100/100**, two-path **3/100** |
| Both-opaque two-path (OpenAI / Composer / Grok) | **1/32 / 0/32 / 0/32** |
| Dual-path | matched **32/32**; novel **0/32**; last-demo copy **0/32** |
| No written hop: protocol / equality recipe | **32/32** all three |
| No written hop: schema list / broken match | **0/32** all three |
| Written hop (LLM) | OpenAI/Grok **32/32**; Composer **28/32** (control) |
| SealRouter on that hop | **32/32** (no LLM; not a reason to call a model) |
| CEO free sealed English | **0/32** (confounded: piecewise hash; person atom typically absent from $q$) |

Models are named **Composer 2.5**, **OpenAI** (`gpt-5.6-sol`), **Grok 4.5**. Result files tagged `auto` are Composer 2.5.

The installable `MiddleLayer` / `SealedChat` package sits between an app and a public LLM. Names stay in the app; the model sees HMAC atoms for one request. **The layer holds the key.** Use a new `MiddleLayer()` per request (`SealedChat.ask` does not rotate the key). Non-Latin names are HMAC'd as Unicode atoms. Vault ints/bools stay JSON numbers.

```
Your app  →  MiddleLayer.call() packs messages  →  SealedChat.ask() sends call.messages
          →  OpenAI  →  unseal on this side
MiddleLayer does not call an LLM. Isolation quiz files (`llm_prompt` / `pack_mut_batch()`) are not the app API.
```

## Install

Python 3.10+. From the root of this repository:

```bash
pip install -e .
pip install -e '.[openai]'   # official OpenAI SDK (optional)
pip install -e '.[dev]'      # pytest
pip install -e '.[paper]'    # matplotlib — rebuild paper figures
```

CI: `.github/workflows/ci.yml` runs pytest on Python 3.10 and 3.12.

**Developers** (this README): `pip install -e .` then `MiddleLayer` / `SealedChat` in your app.
**Scientists / reviewers:** [`SCIENTIST.md`](SCIENTIST.md) — score locked JSON, isolation protocol, bring-your-own graph.
**Contributing / security:** [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md).

## 60-second usage (OpenAI)

```python
import os
from oir import MiddleLayer
from oir.chat import SealedChat, OpenAIChatClient

assert os.environ.get("OPENAI_API_KEY"), "export OPENAI_API_KEY"

PERSON = "Dara Khosrowshahi"
TRIPLES = [
    (PERSON, "in_dept", "Dept_HR"),
    ("Dept_HR", "at_site", "Site_SF"),
    ("Site_SF", "in_city", "San Francisco"),
    ("Other", "in_dept", "Dept_X"),
    ("Dept_X", "at_site", "Site_X"),
    ("Site_X", "in_city", "Austin"),
]
RELS = ["in_dept", "at_site", "in_city"]

layer = MiddleLayer()  # new HMAC key — do this per request
chat = SealedChat(layer, OpenAIChatClient(model="gpt-4o-mini"))

# rels= attaches a written hop (execution control). That saturates.
# It is not the free two-path evaluation (OpenAI 6/32: no PATH, English
# entities, plaintext city).
answer = chat.ask(
    f"Which city is the site of the department of {PERSON} in?",
    names=[PERSON],
    triples=TRIPLES,
    rels=RELS,
    extra_leak_names=["San Francisco", "Austin"],
)
print(answer)  # "San Francisco", or None if the model returns UNKNOWN
```

If a watched name would appear in the payload, `SealedChat` raises `oir.errors.LeakError` and **does not** call the API.

Send `call.messages` / `pack_messages()`. Isolation quiz files (`llm_prompt` / `pack_mut_batch()`) are for the paper protocol, not the app API.

Runnable copies:

```bash
python3 examples/paper_spine.py        # paper H1–H7: engine + locked JSON (no network)
python3 examples/middleware_hr.py      # app → layer → SealRouter stand-in (no network)
python3 examples/layer_app.py          # no network; SealRouter engine ceiling
python3 examples/custom_three_arm.py examples/custom_graph.example.json
OPENAI_API_KEY=... python3 examples/openai_bridge.py
python3 -m pytest tests/ -q
```

More detail: [`examples/README.md`](examples/README.md).

`python3 harness/prove_layer.py` is the same engine ceiling written to `results/prove_layer.json`. It is **not** an LLM score. LLM cells live in `results/seal_layer*.json`. Locked-file map: [`SCIENTIST.md`](SCIENTIST.md), [`bench/README.md`](bench/README.md).

## How a call is packed

1. Bind the start **name** to one graph atom (spaced `Dara Khosrowshahi` → the same token as `Dara_Khosrowshahi`).
2. HMAC every other token in the English question (`EntitySeal.text` splits on non-alphanumerics, so an unbound `Bob Iger` never matches `Bob_Iger`).
3. HMAC the vault / triples (entities **and** relations).
4. Attach a PATH or JOIN binder over those seals.
5. Send OpenAI-shaped messages. Parse `ANSWER_SEALED: <token>`. Unseal on this side.

Without the bind (NOBIND), the start ID never lands in `V(G)` and the public floor is UNKNOWN. Bind + PATH/JOIN is the product layer: an execution control, not the unique-path cell (no PATH, start already in $q$).

### Without the OpenAI extra

Any object with `complete(messages: list[dict]) -> str`:

```python
class Echo:
    def complete(self, messages):
        return "ANSWER_SEALED: UNKNOWN"

from oir import MiddleLayer
from oir.chat import SealedChat
chat = SealedChat(MiddleLayer(), Echo())
```

### API surface

| Symbol | Role |
|--------|------|
| `oir.MiddleLayer` | HMAC key + bind + pack + unseal. `new_call()` / new instance per request. |
| `oir.layer.LayerCall` | `sealed_question`, `messages`, `llm_prompt`, `leaked`, `binder` |
| `oir.chat.SealedChat` | `ask(...)` / `prepare(...)` — raises `LeakError` |
| `oir.errors.LeakError` | Watched plaintext would have appeared in `call.messages`; send is refused |
| `oir.chat.ChatCompleter` | Protocol: `complete(messages) -> str` |
| `oir.chat.OpenAIChatClient` | Thin `openai` wrapper. `gpt-4o-mini`: `temperature=0`. `gpt-5*`: omit temperature, `max_completion_tokens=512` (paper runner). |
| `oir.EntitySeal` / `oir.SealRouter` | Atom HMAC and exact PATH executor (paper ceiling) |

## What this is not

- Not cryptographic secrecy. Deterministic HMAC preserves equality; a crib/frequency script can recover short seals. LLM `UNKNOWN` ≠ confidentiality.
- Not HIPAA, IND-CPA, or a vendor vault eval.
- Not the paper’s isolation quizzes. Those files are `runs/`. This OpenAI adapter is the product-shaped API.
- Unique-path no-plan cells (start in $q$) are a **different** measurement from **LAYER** (name-bind + JOIN/PATH).
- Isolation (one quiz per file) is the public floor for HMAC quizzes. Batched shared-HMAC files can fake SPAN/CROSS success.
- Not CodeS / GPU training. Not a Spider or 2Wiki leaderboard.

## Paper

Repository: https://github.com/pankajnits/oir
PDF: [`paper/arxiv_upload/main.pdf`](paper/arxiv_upload/main.pdf).
arXiv zip: [`paper/oir-arxiv.zip`](paper/oir-arxiv.zip).
Compile: **[`paper/README.md`](paper/README.md)**.
Reproduce and swap datasets: **[`SCIENTIST.md`](SCIENTIST.md)**.

The table at the top of this README is the public spine. Cite `results/factorial_2x2_iso_*.json`, `results/factorial_2x2_iso_shuffle_gpt56.json` (listing order), `results/entity_rel_2x2_iso_*.json`, `results/adv_induction_n32_iso_*.json`, and the identifiability harnesses (`seal_layer_legend_small_n32_harness_*.json`, `opaque_iso_json_n32_harness_*.json`). The CEO three-arm (`ceiling_three_arm_n32_iso_*.json`) is a missing-start / execution-bound cell, not the $2{\times}2$. Missing cells are `n.r.`, not 0.

## Layout

```
oir/            installable library (MiddleLayer, SealedChat)
examples/       app demos (engine ceiling, OpenAI bridge, bring-your-own graph)
tests/          no-network unit tests
paper/          preprint TeX, PDF (`arxiv_upload/main.pdf`), figures
bench/          public OIR-Bench map
harness/        builders and scorers
tools/          harness shim (SealRouter re-export; older compilers)
runs/           isolated quizzes (one file per item)
results/        locked JSON scores
data/           small graphs shipped here; large dumps documented, not vendored
```

## Reproduce a locked JSON

```bash
python3 harness/wilson_cis.py
python3 harness/score_ceiling_n32_iso.py gpt56
# 2x2 / identifiability (from repo root):
# python3 harness/factorial_2x2_iso.py score ...  (see SCIENTIST.md)
python3 examples/custom_three_arm.py examples/custom_graph.example.json
# isolation quizzes: one quiz per file under runs/<suite>/
```

Third-party dumps (Spider, 2Wiki, WTQ) are **not** in this clone. See [`data/README.md`](data/README.md).

## License

Apache-2.0 for original code (see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)). Datasets keep their own licenses (Wikidata CC0; 2WikiMultihopQA Apache-2.0; Spider CC-BY-SA-4.0; OSV CC-BY-4.0).
