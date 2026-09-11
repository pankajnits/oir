# Contributing

## Install

```bash
pip install -e '.[dev]'
python3 -m pytest tests/ -q
ruff check oir tests examples
```

Python 3.10+. Do not commit API keys, `.env`, or `credentials.json`. Isolation runners use `OPENAI_API_KEY` (OpenAI Chat Completions) or `AGENT_API_KEY` / `CURSOR_API_KEY` (Composer 2.5 / Grok 4.5 via Cursor's `cursor_sdk`; optional extra `pip install -e '.[cursor]'`). Issues: https://github.com/pankajnits/oir/issues

The paper affiliation is independent. Public git commits may show a work address; do not treat that as the publication affiliation.

## Layout

- `oir/` — public library (`MiddleLayer`, `SealedChat`). Keep this importable with no extra deps.
- `tests/` — no-network unit tests (CI).
- `examples/` — developer + bring-your-own-graph scripts. `paper_spine.py` walks the paper cells (engine + locked JSON, no LLM).
- `harness/` + `runs/` + `results/` — paper measurement. Do not treat `n.r.` / missing as 0.
- `paper/` — preprint source and PDF (`paper/arxiv_upload/main.pdf`). Rebuild with tectonic (see `paper/README.md`).

## Protocol if you add a quiz

Isolation: one item per file, gold only in harness JSON. Seal entities **and** relations on opacity arms. Do not put PATH on the free sealed English arm.

## PRs

Keep the middle-layer API stable (`oir.MiddleLayer`, `oir.SealedChat`, `LeakError`). Paper JSON locks are append-only unless you are correcting a disclosed scoring bug. Tests must read committed `runs/` and `results/` files; do not call harness `build()` from CI (some rebuilds need dumps that are not vendored).
