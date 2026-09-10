# OIR-Bench (public measurement lock)

Frozen isolation suites for opaque isomorphic reasoning. Gold lives in harness JSON, not in the model-visible prompt. Seals are lexicon hiding, not confidentiality. Missing cells are `n.r.`, never zeros. Result files tagged `auto` are Cursor Composer 2.5.

The **primary** isolation is the Wikidata matched $2{\times}2$ (start in $q$, relations sealed, entities English). The CEO three-arm is a missing-start / execution-bound cell, not that factorial.

## Suites

| Suite | n | Protocol | What it measures | Prompts | Scorer |
|-------|---|---------|------------------|---------|--------|
| Wikidata matched $2{\times}2$ | 32 | isolation, per-item HMAC on relations | English vs opaque relations × unique vs two paths | `runs/factorial_2x2_iso/` | `harness/score_factorial_2x2.py` |
| Three-arm CEO | 32 | isolation, per-item HMAC | plaintext plan vs sealed plan vs free sealed English | `runs/ceiling_three_arm_n32_iso/` | `harness/score_ceiling_n32_iso.py` |
| Dual-path elicitation | 32×5 | isolation | matched-relation vs novel-relation vs explicit plan | `runs/adv_induction_n32_iso/` | `harness/score_adv_n32_iso.py` |
| Non-LLM ceilings | 200 | frozen split | SealRouter / BM25 / gold SQL | `results/oir_bench_baselines.json` | already scored |
| G-Rev2 typed-sink | 200 holdout | synthetic | learned structure vs unique-edge vs lexicon | `data/synthetic/grev2_typed_sink_holdout.jsonl` | `harness/grev2_typed_sink.py` |

Manifest: `bench/MANIFEST.json`.

## Wikidata $2{\times}2$ (primary)

Arms: `ENG_UNIQUE`, `ENG_AMBIG`, `OPAQUE_UNIQUE`, `OPAQUE_AMBIG` (+ plan control). Locked OpenAI: English unique/two-path **31/32**, opaque unique **32/32**, opaque two-path **6/32**. JSON: `results/factorial_2x2_iso_{gpt56,composer25,grok45}.json`.

## Three-arm (missing-start / execution bound)

Arms: `PLAIN_PROG`, `SEAL_PROG`, `SEAL_NL`. One quiz per file. Answer format:

```
ANSWER_PLAIN[<id>]: <city_or_UNKNOWN>
ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>
```

Locked free-form: Cursor Composer 2.5, OpenAI `gpt-5.6-sol`, and Grok 4.5 at `32/32 ≈ 32/32 ≫ 0/32`. Dual-path free-form tags: `gpt56`, `grok45ff`, `composer25ff`.

Bring-your-own graph (engine ceiling, no LLM): `python3 examples/custom_three_arm.py examples/custom_graph.example.json` — see [`SCIENTIST.md`](../SCIENTIST.md).

## Dual-path (elicitation ≠ composition)

Paper names vs suite ids: matched-asymmetric `SAME_TRAP`, novel-asymmetric `CROSS_TRAP`, matched-balanced `SAME_BALANCED`, novel-balanced `CROSS_BALANCED`, explicit plan `PATH_TRAP`.

Do **not** run `harness/induce_follow_n32_iso.py` or `run_induce_mut_n32_iso.py` if the claim is free-form. Those are sealed-demo binding. Free-form locks: `adv_induction_n32_iso_{gpt56,grok45ff,composer25ff}.json`.

## Non-LLM

SealRouter is an exact joiner on sealed triples (CEO-CF **200/200**). Gold Spider SQL in sqlite is **191/200**. BM25 is the lexical floor. An LM that saturates sealed plans is approximating this executor, not beating it.

## G-Rev2 (copy vs bind, learned)

Typed-sink PATH programs: unique-edge SealRouter **0/200**, global count lexicon **0/200**, typed-sink symbolic **200/200**, prompt-local structural logreg **200/200**. Tiny Transformer without PATH-matched adjacency stays near **101/200**. Not G-Rev1 (PATH is given).

## Reproduce a model cell

```bash
# score existing replies
python3 harness/score_factorial_2x2.py gpt56 factorial_2x2_iso_harness
python3 harness/score_ceiling_n32_iso.py gpt56
python3 harness/score_adv_n32_iso.py gpt56
python3 harness/score_copy_vs_bind_n32.py gpt56
```

OpenAI isolation three-arm: `OPENAI_API_KEY python3 harness/run_openai_ceiling_n32_iso.py`

Do not commit API keys.
