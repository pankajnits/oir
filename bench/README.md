# OIR-Bench (public measurement lock)

Frozen isolation suites for opaque isomorphic reasoning. Gold lives in harness JSON, not in the model-visible prompt. Seals are lexicon hiding, not confidentiality. Missing cells are `n.r.`, never zeros. Result files tagged `auto` are Composer 2.5.

The **primary** isolation is the Wikidata matched $2{\times}2$ (start in $q$, relations sealed, entities English). The CEO three-arm is a missing-start / execution-bound cell, not that factorial.

## Suites

| Suite | n | Protocol | What it measures | Prompts | Scorer |
|-------|---|---------|------------------|---------|--------|
| Wikidata matched $2{\times}2$ | 32 | isolation, per-item HMAC on relations | English vs opaque relations × unique vs two paths | `runs/factorial_2x2_iso/` | `harness/score_factorial_2x2.py` |
| Wikidata matched $2{\times}2$ n=200 | 200 | city-typed QID freeze, isolation | same $2{\times}2$ on P169/P159/P31 cities | `runs/factorial_2x2_iso_n200/` | `harness/score_factorial_2x2.py gpt56n200 factorial_2x2_iso_n200_harness` |
| Header × decoy ablation | 32×7 | isolation, Wiki-H5 keys, arm-neutral ids | ARM header × cyclic vs constant decoy | `runs/header_decoy_ablation_iso/` | `harness/header_decoy_ablation_iso.py` |
| Header × decoy n=200 | 200×7 | same HMAC as Wiki-H5 n=200 | 4096/medium seven-arm lock; 512 queried H5-cyclic only | `runs/header_decoy_ablation_iso_n200/` | `harness/header_decoy_ablation_iso.py score gpt56n200abl header_decoy_ablation_iso_n200_harness` |
| Wikidata listing shuffle n=200 | 200 | isolation; gold vs decoy listed first | listing-order check (OA **59/200**, 25/100 vs 34/100 ns) | `runs/factorial_2x2_iso_n200/` | `harness/score_factorial_2x2.py gpt56n200 factorial_2x2_iso_shuffle_n200_harness` |
| Three-arm CEO | 32 | isolation, per-item HMAC | plaintext plan vs sealed plan vs free sealed English | `runs/ceiling_three_arm_n32_iso/` | `harness/score_ceiling_n32_iso.py` |
| Dual-path elicitation | 32×5 | isolation | matched-relation vs novel-relation vs explicit plan | `runs/adv_induction_n32_iso/` | `harness/score_adv_n32_iso.py` |
| Non-LLM ceilings | 200 | frozen split | SealRouter / BM25 / gold SQL | `results/oir_bench_baselines.json` | already scored |
| G-Rev2 typed-sink | 200 holdout | synthetic | learned structure vs unique-edge vs lexicon | `data/synthetic/grev2_typed_sink_holdout.jsonl` | `harness/grev2_typed_sink.py` |

Manifest: `bench/MANIFEST.json`.

## Wikidata $2{\times}2$ (primary)

Arms: `ENG_UNIQUE`, `ENG_AMBIG`, `OPAQUE_UNIQUE`, `OPAQUE_AMBIG` (+ plan control). Powered OpenAI freeze (`factorial_2x2_iso_n200_gpt56n200.json`): unique **200/200**, English two-path **199/200**, named-arm opaque two-path **38/200** (UNK 151, decoy 11). Hashed-id unique-path no ARM (`unique_no_arm_iso_n200_gpt56n200uninone.json`) **200/200** at 512 tokens; n=32 city **26/26** (`unique_no_arm_iso_gpt56uninone.json` overall **27/32**). Header×decoy n=200 (`gpt56n200abl`): cyclic/constant no ARM **174/151**, H5 **129/44**, K2 **179/144**. English no ARM cyclic **197/200** (McNemar vs opaque **25 vs 2**). H5 vs no-ARM constant McNemar **4 vs 111**. Hashed-id H5-cyclic at 512 tokens **134/200** (UNK 44, decoy 20, other 1, `NO_OUTPUT` 1; other arms in `gpt56n200h512` are missing, not scores). Alias k=3 does not replace those locks: named-arm **38/46/43**, hashed-id **134/130/127** (`factorial_2x2_iso_n200_gpt56n200k3r{2,3}.json`, `header_decoy_ablation_iso_n200_gpt56n200h512k3r{2,3}.json`). n=32 discovery lock: English unique/two-path **31/32**, opaque unique **32/32**, opaque two-path **6/32** (UNK 24, decoy 2). Same-snapshot rerun: **5/32** (`factorial_2x2_iso_gpt56sep.json`). Arm-neutral header×decoy n=32 (`header_decoy_ablation_iso_{gpt56abl,composer25abl,grok45abl}.json`): H5+cyclic **20/6/0**; no ARM+cyclic **25/21/6**; English no ARM **29/26/24**. Composer English two-path **26/32** → opaque **10/32**; Grok **4/32** → **1/32**. JSON: `results/factorial_2x2_iso_{gpt56,composer25,grok45}.json`. n=200 does not rewrite n=32.

## Three-arm (missing-start / execution bound)

Arms: `PLAIN_PROG`, `SEAL_PROG`, `SEAL_NL`. One quiz per file. Answer format:

```
ANSWER_PLAIN[<id>]: <city_or_UNKNOWN>
ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>
```

Locked free-form: Composer 2.5, OpenAI `gpt-5.6-sol`, and Grok 4.5 at `32/32 ≈ 32/32 ≫ 0/32`. Dual-path free-form tags: `gpt56`, `grok45ff`, `composer25ff`.

Bring-your-own graph (engine ceiling, no LLM): `python3 examples/custom_three_arm.py examples/custom_graph.example.json` — see [`SCIENTIST.md`](../SCIENTIST.md).

## Dual-path (elicitation ≠ composition)

Paper names vs suite ids: matched-asymmetric `SAME_TRAP`, novel-asymmetric `CROSS_TRAP`, matched-balanced `SAME_BALANCED`, novel-balanced `CROSS_BALANCED`, explicit plan `PATH_TRAP`.

Do **not** run `harness/induce_follow_n32_iso.py` or `run_induce_mut_n32_iso.py` if the claim is free-form. Those are sealed-demo binding. Free-form locks: `adv_induction_n32_iso_{gpt56,grok45ff,composer25ff}.json`. Tags: `auto` = Composer 2.5 on some packaging cells; `composer25` / `grok45` = isolation roster; `*ff` = dual-path free-form; `induce` = sealed demos; `mistral` / `qwen35` = local Ollama, not the three-family roster (plan n.r.). An ARM-banner Movie-B variant (`...arm_banner_v1.json`, two-path **25/100**) is not Condition B (locked topology header **3/100**).

## Non-LLM

SealRouter is an exact joiner on sealed triples (CEO-CF **200/200**). Gold Spider SQL in sqlite is **191/200**. BM25 is the lexical floor. An LM that saturates sealed plans is approximating this executor, not beating it.

## G-Rev2 (copy vs bind, learned)

Typed-sink PATH programs: unique-edge SealRouter **0/200**, global count lexicon **0/200**, typed-sink symbolic **200/200**, prompt-local structural logreg **200/200**. Tiny Transformer without PATH-matched adjacency stays near **101/200**. Not G-Rev1 (PATH is given).

## Reproduce a model cell

```bash
# score existing replies
python3 harness/score_factorial_2x2.py gpt56 factorial_2x2_iso_harness
# refuses if the score JSON already exists; --force overwrites a lockfile
python3 harness/header_decoy_ablation_iso.py score gpt56abl
python3 harness/score_ceiling_n32_iso.py gpt56
python3 harness/score_adv_n32_iso.py gpt56
python3 harness/score_copy_vs_bind_n32.py gpt56
```

OpenAI isolation three-arm: `OPENAI_API_KEY=... python3 harness/run_openai_ceiling_n32_iso.py`

Do not commit API keys.
