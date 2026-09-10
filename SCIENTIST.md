# For scientists and reviewers

This repo is a measurement lock plus an installable middle layer. Cite locked JSON; do not treat `missing` or `n.r.` as 0.

Paper PDF: [`paper/arxiv_upload/main.pdf`](paper/arxiv_upload/main.pdf).
Repository: https://github.com/pankajnits/oir

## What you can verify without an LLM or paid API

```bash
pip install -e '.[dev]'
python3 -m pytest tests/ -q
python3 examples/paper_spine.py
python3 examples/layer_app.py
python3 examples/middleware_hr.py
python3 examples/custom_three_arm.py examples/custom_graph.example.json
python3 harness/prove_layer.py
python3 harness/wilson_cis.py
python3 harness/score_ceiling_n32_iso.py gpt56
python3 harness/score_adv_n32_iso.py gpt56
python3 harness/score_copy_vs_bind_n32.py gpt56
```

`SealRouter` is the symbolic ceiling: if the engine cannot join, a model should not be scored as failing opacity.

## Locked isolation suites (OIR-Bench)

Prompts: `runs/<suite>/item_*/prompt.txt` (gold is **not** in the prompt).
Harness JSON: `results/<suite>_harness.json`.
Scorers: `harness/score_*.py`.

| Suite | Scorer | Locked free-form JSON |
|-------|--------|------------------------|
| Wikidata $2{\times}2$ n=32 | `factorial_2x2_iso.py` + iso harness runners | `results/factorial_2x2_iso_{gpt56,composer25,grok45}.json` |
| Wikidata two-path listing shuffle n=32 | `factorial_2x2_iso_shuffle.py` + `score_factorial_2x2.py gpt56 factorial_2x2_iso_shuffle_harness` | `results/factorial_2x2_iso_shuffle_gpt56.json` |
| WikiMovies / MetaQA n=100 Condition A | `harness/metaqa_2x2_people_n100.py` | `results/metaqa_2x2_people_n100_iso_{gpt56,composer25,grok45}.json` (OpenAI two-path **96/100**; on the 32 names shared with Movie-A32, **29/32**) |
| WikiMovies/MetaQA-derived n=100 Condition B (OpenAI) | `harness/metaqa_2x2_people_n100_qhash.py` | `results/metaqa_2x2_people_n100_qhash_iso_gpt56.json` (unique **100/100**, two-path **3/100**) |
| Entity×relation n=32 | `entity_rel_2x2_iso.py` | `results/entity_rel_2x2_iso_*.json` |
| Dual-path n=32 | `score_adv_n32_iso.py {gpt56,grok45ff,composer25ff}` | `results/adv_induction_n32_iso_*.json` |
| Identifiability n=32 (no hop) | `seal_layer_legend.py` / `opaque_iso_json.py` `score` | `results/seal_layer_legend_small_n32_harness_*.json`, `opaque_iso_json_n32_harness_*.json` |
| Three-arm n=32 (missing-start cell) | `score_ceiling_n32_iso.py {gpt56,grok45,composer25}` | `results/ceiling_three_arm_n32_iso_*.json` |

Do **not** overwrite `results/adv_induction_n32_iso_grok45.json` (archived binding). The free-form claim is `grok45ff`.

Full map: [`bench/README.md`](bench/README.md).

## Bring your own dataset

1. Write a JSON list like [`examples/custom_graph.example.json`](examples/custom_graph.example.json): `id`, `question`, `start`, `rels`, `triples`, `gold`.
2. Run `python3 examples/custom_three_arm.py your.json`.
3. Engine prints `PLAIN_PROG` / `SEAL_PROG` ceilings (must both saturate if the graph is well-posed).
4. The script writes two NL files (no PATH):
   - `*_BOUND_NL.txt` — start bound into \(q\). Unique-path / copy-and-walk class. **Not** CEO SEAL_NL 0/32.
   - `*_NOBIND_NL.txt` — piecewise HMAC. Use this for the CEO missing-start floor. Spaced names (`Alice Smith` vs graph `Alice_Smith`) must split or the start still lands.
   Neither file is the paper free two-path cell (OpenAI 6/32: no PATH, English entities, plaintext city).
5. Score exact match on the gold **plaintext** after unsealing, or on the sealed token if you keep the same `MiddleLayer` key.

Protocol that matches the paper floor:

- Isolation: one quiz per file.
- Seal **entities and relations**.
- No PATH/JOIN, no legend, no retrieved path on the NL arm.
- Gold lives outside the prompt.
- Per-item HMAC if you claim isolation (see `harness/ceiling_three_arm_n32_iso.py`).

A saturating sealed plan on a new domain does **not** retract CEO free sealed English 0/32. Unique-path graphs with the start already in the question are a different cell.

## Re-running a model cell

OpenAI isolation three-arm (needs `OPENAI_API_KEY`, costs money):

```bash
python3 harness/run_openai_ceiling_n32_iso.py
python3 harness/score_ceiling_n32_iso.py gpt56
```

Composer 2.5 / Grok cells used the same `runs/` files (`AGENT_API_KEY` + `harness/run_iso_agent_harness.py`). Tags `composer25` / `grok45` / `*ff` are reply directories under `results/`. Result files tagged `auto` are Composer 2.5.

## Third-party dumps

Spider sqlite, raw 2Wiki, WTQ/FinQA tables are **not** vendored. Locked scores still cite `results/`. Restore dumps only to rebuild: [`data/README.md`](data/README.md).

## What not to claim from a new dataset

- Excel-style templates that name both predicates in the question are a softer probe than CEO SEAL_NL.
- Copying the last demonstration answer is not binding.
- Seals are lexicon hiding, not confidentiality.
