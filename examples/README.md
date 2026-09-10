# Examples

All of these run from the repository root after `pip install -e .`.
None need a paid API unless you pass `--openai` or run `openai_bridge.py`.

```bash
python3 examples/paper_spine.py        # paper H1–H7 cells: engine + locked JSON (no network)
python3 examples/middleware_hr.py      # app → MiddleLayer → SealRouter stand-in → unseal
python3 examples/layer_app.py          # pack + engine unseal (no SealedChat)
python3 examples/custom_three_arm.py examples/custom_graph.example.json
python3 examples/openai_bridge.py      # same packing; needs OPENAI_API_KEY
python3 -m pytest tests/ -q
```

| Script | What it proves |
|--------|----------------|
| `paper_spine.py` | Paper cells: unique vs two-path, plan control, CEO missing-start, dual-path, WikiMovies Cond. B vs A, entity×relation, generators, identifiability. Engine + locked OpenAI scores. Not a re-run of n=32. |
| `middleware_hr.py` | Product middleware: bind start, HMAC question+graph, refuse leaks, unseal. Fake LLM is `SealRouter` so CI stays green. H2-shaped PATH, not the free two-path cell. |
| `layer_app.py` | Lowest-level `MiddleLayer.call` + `execute_path`. |
| `custom_three_arm.py` | Bring-your-own graph. Engine ceilings for plan arms; writes `*_BOUND_NL.txt` (start in \(q\)) and `*_NOBIND_NL.txt` (piecewise HMAC). Neither is the free two-path 6/32 cell. |
| `openai_bridge.py` | Same HR query over the official OpenAI SDK. Without a key it prints the engine ceiling and exits 0. |
| `custom_graph.example.json` | One 2-hop item for `custom_three_arm.py`. |

Optional live API call for locked Wikidata 2×2 item 0 (unique vs two-path). This is **not** the n=32 lock:

```bash
OPENAI_API_KEY=... python3 examples/paper_spine.py --openai
```

`MiddleLayer` / `SealedChat` hide names from the remote payload. That is lexicon hiding, not confidentiality. Isolation quizzes in `runs/` are the paper measurement, not these app demos.
