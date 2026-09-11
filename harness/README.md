# Measurement harness

Builders and scorers for the paper cells. This is not the installable API (`oir/`).

Start here:

- [`SCIENTIST.md`](../SCIENTIST.md) — clone-and-run checks, locked JSON map
- [`bench/README.md`](../bench/README.md) — OIR-Bench suite table
- [`examples/paper_spine.py`](../examples/paper_spine.py) — engine + locked scores, no network

Do **not** treat `n.r.` / missing as 0. Do **not** call `build()` from tests or CI; rebuilds can require third-party dumps that are not in this clone (`data/README.md`).

Isolation prompts live in `runs/<suite>/`. Gold is in `results/<suite>_harness.json`, not in the prompt.

Composer/Grok: `run_iso_agent_harness.py` (Cursor SDK, `pip install -e '.[cursor]'`). OpenAI: `run_openai_iso_harness.py`. Shared parser: `reply_parse.py` (empty completions are `NO_OUTPUT`). Header × decoy ablation: `header_decoy_ablation_iso.py`. Executed scores: `results/header_decoy_ablation_iso_{gpt56abl,composer25abl,grok45abl}.json` (11 Sep 2026; Composer/Grok `--preamble none`). `results/SHA256SUMS` hashes git-tracked JSON (summaries and reply sidecars) and per-item reply `.txt` files.
