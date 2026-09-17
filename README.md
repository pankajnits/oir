# OIR — Opaque Isomorphic Reasoning

[![CI](https://github.com/pankajnits/oir/actions/workflows/ci.yml/badge.svg)](https://github.com/pankajnits/oir/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Measurement protocol and HMAC middle layer for the paper
*When Can Language Models Join Without Relation Names?*

**Code, isolation quizzes (`runs/`), and locked scores (`results/`):**
[github.com/pankajnits/oir](https://github.com/pankajnits/oir)

**Named preprint TeX** (not the TMLR review upload): [`paper/arxiv_upload/`](paper/arxiv_upload/).
**Anonymous TMLR PDF + zip:** [`paper/tmlr/`](paper/tmlr/) (`main.pdf`, `oir-tmlr-supplementary.zip`).
Do not put this GitHub URL on the OpenReview form.

Pinned clone: tag [`v1.0.6`](https://github.com/pankajnits/oir/releases/tag/v1.0.6).

Cite this repository with [`CITATION.cff`](CITATION.cff).

```bash
git clone https://github.com/pankajnits/oir.git
cd oir
pip install -e '.[dev]'
python3 -m pytest tests/ -q
```

From a checkout you can also `pip install git+https://github.com/pankajnits/oir.git`. The import name is `oir`; the PyPI-style distribution name is `oir-layer`.

Compile the named preprint: `cd paper/arxiv_upload && tectonic -X compile main.tex`
(see [`paper/README.md`](paper/README.md)). That folder is **not** the TMLR
upload. Anonymous review files: `python3 paper/tmlr/convert_from_arxiv.py`
then `cd paper/tmlr && tectonic -X compile main.tex`.

HMAC seals are an **instrument** (instance-wise injective renaming that preserves equality). They are not confidentiality, HIPAA, or IND-CPA. Missing cells are `n.r.`, never zeros.

**Finding (OpenAI n=200 city-typed freeze; Composer/Grok stay at n=32).** Unique sealed routes still execute (English/opaque **200/200**). Under two competing sealed routes, named-arm OpenAI usually answers UNKNOWN (**38/200** gold, UNKNOWN 151, decoy 11), not the decoy: CONTEXT-only, two same-type 2-hops, no written hop. Hashed case ids on the same graphs reduce abstention (UNKNOWN 151→44, gold **134/200**). Exact-match is packing-sensitive, not a packaging-free opacity law (no-ARM English/opaque at 4096/medium is two-path only). The table is the lock inventory; later alias draws do not replace those cells.

## Headline locks

**n=200 is OpenAI-only, one city-typed freeze of people** (alias $k{=}3$ of named-arm and hashed-id below). Composer/Grok stay at n=32. The n=26 city slice with decoy 0 is a discovery note, not the powered rate.

| Cell | Result |
|------|--------|
| Unique path, both-opaque (entities+relations sealed) | **32/32** all three families |
| Unique path, relation-opaque Wikidata 2×2 | OpenAI **32/32**; Composer **27/32**; Grok **30/32** |
| City-typed **n=200** freeze (OpenAI; every HQ is Wikidata city P31, QIDs live-checked) | Unique English/opaque **200/200**, English two-path **199/200**, named-arm opaque two-path **38/200** (UNK 151, decoy 11; Wilson [0.14, 0.25]), plan **200/200**. Hashed-id unique-path no ARM **200/200** at 512 tokens (not matched to two-path no-ARM at 4096/medium). |
| Same freeze, 512-token case-id (ARM kept) | Named-arm **38/200** vs hashed-id H5-cyclic **134/200** (UNK 44, decoy 20, other 1, `NO_OUTPUT` 1). Alias k=3 (does not replace those locks): named-arm **38/46/43** vs hashed-id **134/130/127**. |
| Same freeze, listing shuffle (OpenAI) | Opaque two-path **59/200** (gold-first **25/100** vs decoy-first **34/100**, two-proportion $p{\approx}0.16$). |
| Header × decoy n=200, hashed ids, 4096/medium (OpenAI) | Cyclic/constant: no ARM **174/151**, H5 **129/44**, K2 **179/144**. English no ARM cyclic **197/200** (McNemar vs opaque **25 vs 2**). H5 vs no-ARM constant McNemar **4 vs 111**. |
| WikiMovies Condition A/B n=200 (OpenAI) | A two-path **122/200** (Wiki-H5 topology ARM, not the A100 `n=100` banner; not a resample of **96/100**); B unique **200/200**, two-path **7/200** |
| Both-opaque two-path n=200 (OpenAI) | unique **200/200**, two-path **12/200**, plan **200/200** |
| Dual / CEO-NL n=200 (OpenAI) | Dual matched **200/200**, novel **2/200**, plan **200/200**. CEO-NL sealed plan **200/200**, free sealed English **0/200**. |
| English Wikidata 2×2 n=32 (OpenAI; relations readable) | unique **31/32**, two-path **31/32** |
| Opacity × two paths, n=32 lock (OpenAI) | Named-arm Wiki-H5 **6/32** (UNK 24, decoy 2). Both decoys sit on the six non-city P159 golds. City slice **5/26** (UNK 21, decoy 0) cannot resolve a ~5% decoy rate. |
| Same-date case-id pair, 512 tokens, cyclic (11 Sep n=32) | Named-arm **5/32** vs hashed-id H5-cyclic **20/32** (one `NO_OUTPUT` each; ARM line kept). |
| Header × decoy n=32, hashed ids, 4096/medium | Cyclic/constant: no ARM **25/27**, H5 **20/10**, K2 **30/26**. Composer H5 cyclic **6/32** vs no ARM cyclic **21/32**. Grok H5/K2 **0/32**, no ARM cyclic **6/32**, English no ARM **24/32**. |
| Same graphs, Composer / Grok two-path | Composer English **26/32** → opaque **10/32**; Grok English **4/32** (UNK 28) → opaque **1/32** |
| WikiMovies Condition A n=100 (OpenAI) | two-path **96/100**; on 32 names shared with A32, **29/32** (A32 was **17/32**) |
| WikiMovies Condition B n=100 (OpenAI) | unique **100/100**, two-path **3/100** (hashed verbs + two-hop ARM; archived banner **25/100**) |
| Both-opaque two-path (OpenAI / Composer / Grok) | **1/32 / 0/32 / 0/32** |
| Dual-path | isolation matched **32/32** under both noise regimes; novel asymmetric **0/32** (decoy 8); novel balanced **0/32** (decoy 0). Composer isolation UNKNOWN is a sealed-demo helper; free-form `composer25ff` novel-asymmetric is decoy **32/32**. |
| No written hop: protocol / equality recipe | **32/32** all three |
| No written hop: schema list / broken match | **0/32** all three |
| Written hop (LLM) | OpenAI/Grok **32/32**; Composer **28/32** (control) |
| SealRouter on that hop | **32/32** (no LLM; not a reason to call a model) |
| CEO free sealed English | **0/32** (confounded: piecewise hash; person atom typically absent from $q$) |

Models are named **Composer 2.5**, **OpenAI** (`gpt-5.6-sol`), **Grok 4.5**. Result files tagged `auto` are Composer 2.5.

The installable `MiddleLayer` / `SealedChat` package sits between an app and a public LLM. Names stay in the app; the model sees HMAC atoms for one request. **The layer holds the key.** Use a new `MiddleLayer()` per request (`SealedChat.ask` does not rotate the key). Non-Latin names: pure CJK stays Unicode. Mixed-script Latin is not “ASCII-folded”: any remaining ASCII causes non-ASCII characters to be replaced with `_` (`Zürich` → `Z_rich`; `東京 Tower` and `大阪 Tower` would collide). `EntitySeal(strict=True)` (the default) rejects distinct names that would share a seal; `strict=False` rebuilds legacy locks. Vault ints/bools stay JSON numbers.

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
pip install -e '.[cursor]'   # Cursor Python SDK for Composer/Grok cells
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
python3 examples/paper_spine.py        # paper H1–H4, OA, H6–H8: engine + locked JSON (no network)
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
| `oir.chat.OpenAIChatClient` | Thin `openai` wrapper. `gpt-4o-mini`: `temperature=0`. `gpt-5*`: omit temperature, `max_completion_tokens=4096` (paper isolation runner used 512). |
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

The table at the top of this README is the public spine. Cite `results/factorial_2x2_iso_*.json`, `results/factorial_2x2_iso_n200_gpt56n200.json`, `results/factorial_2x2_iso_shuffle_gpt56.json` and `results/factorial_2x2_iso_shuffle_n200_gpt56n200.json` (listing order), `results/header_decoy_ablation_iso_{gpt56abl,composer25abl,grok45abl}.json` (header×decoy, 11 Sep 2026; `--preamble none` for Composer/Grok), `results/header_decoy_ablation_iso_n200_{gpt56n200abl,gpt56n200h512}.json`, `results/entity_rel_2x2_iso_*.json`, `results/adv_induction_n32_iso_*.json`, and the identifiability harnesses (`seal_layer_legend_small_n32_harness_*.json`, `opaque_iso_json_n32_harness_*.json`). The CEO three-arm (`ceiling_three_arm_n32_iso_*.json`) is a missing-start / execution-bound cell, not the $2{\times}2$. Missing cells are `n.r.`, not 0. Verify evidence with `shasum -c results/SHA256SUMS`.

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
