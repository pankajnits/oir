# Measurement harness

Builders and scorers for the paper cells. This is not the installable API (`oir/`).

Start here:

- [`SCIENTIST.md`](../SCIENTIST.md) — clone-and-run checks, locked JSON map
- [`bench/README.md`](../bench/README.md) — OIR-Bench suite table
- [`examples/paper_spine.py`](../examples/paper_spine.py) — engine + locked scores, no network

Do **not** treat `n.r.` / missing as 0. Do **not** call `build()` from tests or CI; rebuilds can require third-party dumps that are not in this clone (`data/README.md`).

Isolation prompts live in `runs/<suite>/`. Gold is in `results/<suite>_harness.json`, not in the prompt.
