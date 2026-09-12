# For scientists and reviewers

This repo is a hash-pinned measurement plus an installable middle layer. Cite locked JSON and reply files; do not treat `missing` or `n.r.` as 0. Check hashes: `shasum -c results/SHA256SUMS` (JSON summaries, reply sidecars, and per-item `.txt` replies).

Paper PDF: [`paper/arxiv_upload/main.pdf`](paper/arxiv_upload/main.pdf).
Repository: https://github.com/pankajnits/oir (release tag `v1.0.3`).

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
python3 harness/write_sha256sums.py   # or: shasum -c results/SHA256SUMS
# Isolation scorers refuse to overwrite an existing results/*_{tag}.json
# unless you pass --force. Do not rescore locked tags to ``verify''.
```

`SealRouter` is the symbolic ceiling: if the engine cannot join, a model should not be scored as failing opacity.

## Locked isolation suites (OIR-Bench)

Prompts: `runs/<suite>/item_*/prompt.txt` (gold is **not** in the prompt).
Harness JSON: `results/<suite>_harness.json`.
Scorers: `harness/score_*.py`.

| Suite | Scorer | Locked free-form JSON |
|-------|--------|------------------------|
| Wikidata $2{\times}2$ n=32 | `factorial_2x2_iso.py` + iso harness runners | `results/factorial_2x2_iso_{gpt56,composer25,grok45}.json` (named-arm opaque two-path OpenAI **6/32**; snapshot `gpt56sep` **5/32**) |
| Header × decoy ablation n=32×7 | `header_decoy_ablation_iso.py` | `results/header_decoy_ablation_iso_{gpt56abl,composer25abl,grok45abl}.json` (H5+cyclic OpenAI **20/32**, Composer **6/32**, Grok **0/32**; no ARM+cyclic **25/21/6**; English **29/26/24**). Composer/Grok used `--preamble none`. |
| Wikidata two-path listing shuffle n=32 | `factorial_2x2_iso_shuffle.py` + `score_factorial_2x2.py gpt56 factorial_2x2_iso_shuffle_harness` | `results/factorial_2x2_iso_shuffle_gpt56.json` |
| WikiMovies / MetaQA n=100 Condition A | `harness/metaqa_2x2_people_n100.py` | `results/metaqa_2x2_people_n100_iso_{gpt56,composer25,grok45}.json` (OpenAI two-path **96/100**; on the 32 names shared with Movie-A32, **29/32**, vs A32 **17/32**) |
| WikiMovies/MetaQA-derived n=100 Condition B (OpenAI) | `harness/metaqa_2x2_people_n100_qhash.py` | `results/metaqa_2x2_people_n100_qhash_iso_gpt56.json` (unique **100/100**, two-path **3/100**) |
| Entity×relation n=32 | `entity_rel_2x2_iso.py` | `results/entity_rel_2x2_iso_*.json` |
| Dual-path n=32 | `score_adv_n32_iso.py {gpt56,grok45ff,composer25ff}` | `results/adv_induction_n32_iso_*.json` |
| Identifiability n=32 (no hop) | `seal_layer_legend.py` / `opaque_iso_json.py` `score` | `results/seal_layer_legend_small_n32_harness_*.json`, `opaque_iso_json_n32_harness_*.json` |
| Three-arm n=32 (missing-start cell) | `score_ceiling_n32_iso.py {gpt56,grok45,composer25}` | `results/ceiling_three_arm_n32_iso_*.json` |

Do **not** overwrite `results/adv_induction_n32_iso_grok45.json` (archived binding). The free-form claim is `grok45ff`. Composer isolation-tag novel-relation UNKNOWN files are stamped by `run_induce_mut_n32_iso.py` (sealed-demo helper), not a free Composer completion; cite `composer25ff` for free-form.

Transcript inventory (locked by `tests/test_paper_transcript_inventory.py`):

- **Answer line only:** Composer Wiki-OO `OO_UNIQUE`/`OO_AMBIG`; Composer/Grok CEO three-arm; Dual `composer25ff`/`grok45ff` all arms; Composer Dual isolation `PATH_TRAP`/`SAME_TRAP`; Grok Dual isolation `PATH_TRAP`.
- **One-line tail, not a dump:** Grok Wiki-OO `OO_UNIQUE`/`OO_AMBIG`.
- **Induce helper, not free-form:** Composer Dual isolation `CROSS_*`/`SAME_BALANCED`; Grok Dual isolation `CROSS_*`/`SAME_*`.
- **Transcript or sidecar:** Wiki-H5 named-arm three families; OpenAI Wiki-OO and CEO three-arm; header×decoy `*abl`.

A 12 September 2026 Composer Wiki-OO transcript rerun (`composer25tx`, `--preamble cursor`, current runner) does **not** replace the August lock: unique **32/32** (item 31 gold recovered from a markdown `ANSWER` line in the tail); two-path **0/32** (UNKNOWN 31, decoy 1 vs August UNKNOWN 32). Composer CEO `SEAL_NL` transcript rerun is **0/32** UNKNOWN 32 (PLAIN_PROG/SEAL_PROG not re-queried). Score with `python3 harness/score_factorial_2x2.py composer25tx entity_rel_2x2_iso_harness` and `python3 harness/score_ceiling_n32_iso.py composer25tx`.

Paired McNemar on the header×decoy suite is complete-case (missing and `NO_OUTPUT`/error dropped from the pair). Locked ablation JSON have no incompletes, so stored $p$-values are unchanged. Isolation scorers write through `harness/lockjson.py` (`ensure_ascii=False`, trailing newline, refuse overwrite unless `--force`). The agent canary does not persist an ERROR file. CEO three-arm tags `gpt56` / `composer25` / `grok45` always score `ceiling_n32_iso_replies_*` (the August trees); a new tag uses the populated tree and cannot be shadowed by an empty harness-stem directory.

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

Composer 2.5 / Grok 4.5 cells used the same `runs/` files through Cursor's agent SDK (`AGENT_API_KEY` or `CURSOR_API_KEY` + `harness/run_iso_agent_harness.py`), not a vendor chat API. The runner's default `--preamble cursor` prefixes a reply-only instruction OpenAI never received; `--preamble none` sends the prompt file verbatim. Tags `composer25` / `grok45` / `*ff` are reply directories under `results/`. Do not reuse those tags for new suites. Result files tagged `auto` are Composer 2.5. Dual-path free-form is `composer25ff` / `grok45ff`; `grok45.json` is archived binding; `induce` is sealed-demo binding, not free-form. Local `mistral` / `qwen35` dual-path JSONs are not in the three-family roster (plan n.r.).

Header × decoy ablation (11 September 2026): `results/header_decoy_ablation_iso_{gpt56abl,composer25abl,grok45abl}.json`. Named-arm Wiki-H5 snapshot check: `results/factorial_2x2_iso_gpt56sep.json` (**5/32**, 1 `NO_OUTPUT`, OpenAI OPAQUE_AMBIG only; other arms `n.r.` / `missing` 32 are not scores). Composer/Grok used `--preamble none`. Empty completions are `NO_OUTPUT` on new runner files; `--retry-empty` re-queries legacy empty files stored as UNKNOWN. `score_factorial_2x2.py` refuses to overwrite an existing score JSON unless `--force`.

## Third-party dumps

Spider sqlite, raw 2Wiki, WTQ/FinQA tables are **not** vendored. Locked scores still cite `results/`. Restore dumps only to rebuild: [`data/README.md`](data/README.md).

## What not to claim from a new dataset

- Excel-style templates that name both predicates in the question are a softer probe than CEO SEAL_NL.
- Copying the last demonstration answer is not binding.
- Seals are lexicon hiding, not confidentiality.
