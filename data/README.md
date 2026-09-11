# Data shipped vs data you download

This clone ships **small** graphs used by the layer demo and several locked JSON cells. Full third-party dumps are not vendored (~100MB tree with locked `results/` and `runs/`).

**Cite locked JSON; do not treat `missing: n` as a score of 0.** Re-running ENGINE/WTQ rebuilds needs the dumps below.

## In this repo

| Path | Role |
|------|------|
| `real/wikidata_ceo_hops_v2.json` | CEO → company → HQ (three-arm / 2×2 / entity-rel). Wikidata-derived, CC0. |
| `metaqa/oir_2hop_people_n100.json` | WikiMovies people freeze n=100 |
| `metaqa/oir_official_2hop_n32.json` | MetaQA-style 2-hop template freeze (not 14k test) |
| `wiki_cf_n200.json` | 2Wiki-CF n=200 items (not the raw 2Wiki dump) |
| `2wiki_compositional_n12.json`, `_n200.json` | Compositional slices |
| `spider_oir_n12.json`, `spider_oir_n200.json`, `spider_join_n8.json` | Spider **items**, not the sqlite DBs |
| `osv_advisories_n8.json` | Small OSV slice |
| `synthetic/*.jsonl` | G-Rev2 typed-decoy / path **holdouts**; `grev2_typed_sink_train.jsonl` is only for GNN rebuilds (cite `results/grev2_*.json` if you do not retrain) |
| `real_docs/` | Messy-doc style pages. `opendata500_us_companies.csv` is OpenData500 US companies metadata (license not stated in-file; treat as third-party, confirm before redistribution). |

Not shipped: `2wiki_compositional_dev.json` (needed only to *rebuild* the CF freeze — `harness/freeze_wiki_cf.py` reads that filename, **not** a `data/2wiki` parquet dump). `sealed_path_train.jsonl` (G-Rev2 train; holdouts above are enough to score locked cells). G-Rev2 GNN/Transformer scripts need `pip install -e '.[torch]'`; cite `results/grev2_*.json` if torch is absent — do not score that as 0. Spider-derived JSON items in this clone inherit Spider's CC BY-SA 4.0; the repo license is Apache-2.0.

Do not run `baselines_oir.py` after restoring `data/spider` unless you intend to rewrite `results/oir_bench_baselines.json` (ENGINE **191/200**). Without the dump, that script skips Spider and does not overwrite the lockfile.

## What you can run without dumps or an LLM

```bash
pip install -e '.[dev]'
python3 -m pytest tests/ -q
python3 examples/layer_app.py
python3 harness/prove_layer.py
python3 harness/baselines_oir.py   # wiki BM25 / SealRouter; skips Spider if dumps missing
python3 harness/wilson_cis.py
pip install -e '.[paper]' && python3 harness/make_paper_figures.py
```

Wiki CF BM25 / SealRouter use `wiki_cf_n200.json` only. Spider ENGINE **191/200** is already locked in `results/oir_bench_baselines.json`; do not overwrite it unless you have the sqlite dump.

`tools/` is a thin harness shim (`SealRouter` re-exports `oir.SealRouter`; `nl_to_path_compiler`, `sealprobe`, `copy_constrained_gate` for older builders). Canonical product API is `oir/`.

## Not vendored

Download from upstream (not in this clone):

| Dump | License | Upstream |
|------|---------|----------|
| Spider (`spider_data.zip`) | CC-BY-SA-4.0 | https://yale-lily.github.io/spider |
| WikiMovies KB (`wiki_entities_kb.txt`) | as labeled upstream (third-party MetaQA mirror; confirm before redistribution) | https://github.com/rohit129/Movie_KnowledgeGraph_QA (MetaQA movie graph) |
| 2WikiMultihopQA | Apache-2.0 | https://github.com/Alab-NII/2wikimultihop |
| WikiTableQuestions / FinQA / FeTaQA | as labeled | respective project pages |

Unzip those dumps next to `data/` if you need to *rebuild* Spider ENGINE / WTQ cells. Locked JSON in `results/` is enough to cite. These rebuilds need the dumps: `harness/spider_oir.py`, `spider_sql_n32.py`, `spider_heuristic_sql.py`, `freeze_spider_n200.py`, `wtq_dsl_fix.py`, `complex_bench.py`, `real_complex_long_verify.py`. `realqa_2x2.py` `build()` hits WTQ even though CEO/2Wiki slices ship. `subjective_oir.py` skips FeTaQA if missing.

`results/phase2_iter21_*.json` points at `runs/phase2_iter21/`, which is not in this clone (early encoding; not the paper spine).

Subsequent public graphs (OpenSanctions, GLEIF, …) are **not** downloaded here.
