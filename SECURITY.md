# Security

This project is **lexicon hiding**, not a confidentiality system. HMAC seals preserve equality inside one call. Do not treat model `UNKNOWN` as a privacy proof.

- Do not open GitHub issues that paste real PII, production keys, or private graphs.
- Report suspected leakage in `MiddleLayer.pack_messages` / `leak_check` by describing the API call, not by attaching secrets.
- `leak_check` scans on-wire `messages` only, not isolation quiz files (`llm_prompt` / `pack_prompt`). A watched string that appears only as `cid` in an isolation header is not a send leak.
- Protocol English (`PATH_QUERY`, `JOIN_QUERY`, `UNKNOWN`) can false-positive if you add those tokens to the watchlist; they are not plaintext names.
- `OPENAI_API_KEY` and `AGENT_API_KEY` stay in the environment. Never commit them.

See `LICENSE` (Apache-2.0, AS IS).
