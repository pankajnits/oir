"""Middle layer: app English / vault plaintext → LLM seals → app plaintext.

Lexicon hiding (not IND-CPA):
  Names stay on this side. The remote LLM sees HMAC atoms for
  one call, optional PATH/JOIN binders, and never a name→seal legend.
  Per-call keys: equality holds inside one message; yesterday's seals are junk.

PATH uses ``path_program`` (English PATH_QUERY glue, HMAC relation atoms):
the paper H2 execution control, not the free two-path 6/32 cell.

JOIN HMAC's leftover English in ``join_steps`` (including verbs).
``harness/seal_layer.py`` keeps English JOIN glue
(``In array … match … take``) and HMAC only keys/values.
``harness/prove_layer.py`` is the engine ceiling, not an LLM cell.

Product HMAC's names *and* relations and scores ANSWER_SEALED.
The primary Wikidata 2×2 HMAC's relations only; entities stay English;
answers are plaintext cities. Seals ≠ confidentiality. The layer holds the key.
"""
from __future__ import annotations

import json
import re
import secrets
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import EntitySeal, SealRouter, path_program

__all__ = [
    "LayerCall",
    "MiddleLayer",
    "bind_span",
    "leak_check",
    "seal_question",
]

LLM_SYSTEM = (
    "You answer over opaque HMAC identifiers. Do not decrypt. Do not use world knowledge. "
    "Use CONTEXT only. If more than one reading is possible, output UNKNOWN. "
    "Reply with exactly one line: ANSWER_SEALED: <token_or_UNKNOWN>"
)


def seal_question(q: str, sealer: EntitySeal, protect: set[str]) -> str:
    """HMAC every token except already-bound START seals."""
    out = []
    for p in EntitySeal.pieces(q):
        if p in protect:
            out.append(p)
        elif EntitySeal.is_atom_token(p):
            out.append(sealer.atom(p))
        else:
            out.append(p)
    return "".join(out)


def bind_span(text: str, name: str, start_seal: str) -> tuple[str, bool]:
    """Replace spaced/raw name spans with the graph atom. Inject if no span hit."""
    variants = {name, name.replace("_", " "), EntitySeal.normalize(name)}
    out, hit = text, False
    for v in sorted((x for x in variants if x), key=len, reverse=True):
        nxt, n = re.subn(
            rf"(?<!\w){re.escape(v)}(?!\w)",
            start_seal,
            out,
            flags=re.I | re.UNICODE,
        )
        if n:
            out, hit = nxt, True
    injected = False
    if start_seal not in out:
        out = f"{out} {start_seal}"
        injected = True
    return out, injected or not hit


def seal_json(obj: Any, sealer: EntitySeal) -> Any:
    """HMAC strings and keys. Ints/bools/null stay JSON-native (not lexicon)."""
    if isinstance(obj, Mapping):
        return {sealer.atom(str(k)): seal_json(v, sealer) for k, v in obj.items()}
    if isinstance(obj, list):
        return [seal_json(v, sealer) for v in obj]
    if isinstance(obj, str):
        return sealer.atom(obj)
    return obj


def leak_check(blob: str, names: Iterable[str]) -> list[str]:
    """Watchlist hit on a blob. Callers must pass the on-wire text, not MUT files."""
    hits = []
    seen: set[str] = set()
    for n in names:
        if not n or n in seen:
            continue
        if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", blob, re.I | re.UNICODE):
            hits.append(n)
            seen.add(n)
    return hits


@dataclass
class LayerCall:
    """One LLM round-trip as packed by the layer."""

    app_question: str
    llm_prompt: str
    sealed_question: str
    start: str
    binder: str
    gold_seal: str | None = None
    start_injected: bool = False
    leaked: list[str] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)

    def unseal(self, layer: MiddleLayer, token: str) -> str | None:
        return layer.unseal(token)


class MiddleLayer:
    """Trusted bridge. New instance (or new_call) ⇒ new HMAC key."""

    def __init__(self, key: bytes | None = None, *, prefix: str = "E", nbytes: int = 6):
        self._key = key if key is not None else secrets.token_bytes(16)
        self.sealer = EntitySeal(self._key, prefix=prefix, nbytes=nbytes)

    def new_call(self) -> MiddleLayer:
        return MiddleLayer(prefix=self.sealer.prefix, nbytes=self.sealer.nbytes)

    def atom(self, value: str) -> str:
        return self.sealer.atom(value)

    def bind_name(self, display: str) -> str:
        return self.sealer.atom(display)

    def nobind_question(self, english: str) -> str:
        """HMAC the English question as typed (spaced names split). Floor."""
        return self.sealer.text(english)

    def seal_question_bound(self, english: str, names: Sequence[str]) -> tuple[str, str, bool]:
        """Bind first name as START, HMAC the rest. Returns (sealed_q, start, injected)."""
        start_raw = names[0]
        start = self.bind_name(start_raw)
        bound, injected = bind_span(english, start_raw, start)
        protect = {self.bind_name(n) for n in names}
        return seal_question(bound, self.sealer, protect), start, injected

    def seal_vault(self, obj: Any) -> Any:
        return seal_json(obj, self.sealer)

    def seal_triples(self, triples: Sequence[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
        return [self.sealer.triple(*t) for t in triples]

    def _as_atom(self, s: str) -> str:
        return s if self.sealer.is_hmac_atom(s) else self.atom(s)

    def path_binder(self, start: str, rels: Sequence[str]) -> str:
        rels_s = [self._as_atom(r) for r in rels]
        start_s = self._as_atom(start)
        return path_program(start_s, rels_s).body

    def join_binder(self, start: str, steps: Sequence[str]) -> str:
        """HMAC leftover English in steps (stricter than locked LAYER glue)."""
        start_s = self._as_atom(start)
        protect = set(self.sealer.fwd.values())
        sealed_steps = [seal_question(s, self.sealer, protect) for s in steps]
        return "\n".join(["JOIN_QUERY", f"START {start_s}", *sealed_steps, "Return that atom."])

    def unseal(self, token: str) -> str | None:
        t = token.strip()
        plain = self.sealer.rev.get(t)
        if plain is not None:
            return plain
        return self.sealer.rev.get(t.split()[0]) if t else None

    def execute_path(self, triples: Sequence[tuple[str, str, str]], start: str, rels: Sequence[str]) -> list[str]:
        sealed = self.seal_triples(triples)
        start_s = self.atom(start)
        rels_s = [self.atom(r) for r in rels]
        return SealRouter(sealed).path(start_s, rels_s)

    def pack_messages(
        self,
        sealed_q: str,
        binder: str,
        context: str,
    ) -> list[dict[str, str]]:
        """OpenAI-shaped messages. App-facing; no MUT isolation header."""
        parts = ["QUESTION (token-HMAC'd):", sealed_q, ""]
        if binder:
            parts += [binder, ""]
        parts += ["CONTEXT:", context]
        return [
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user", "content": "\n".join(parts)},
        ]

    def pack_prompt(
        self,
        cid: str,
        sealed_q: str,
        binder: str,
        context: str,
        *,
        header: str | None = None,
    ) -> str:
        """Isolation MUT file (paper protocol). Apps should send pack_messages()."""
        hdr = header or (
            "ARM LAYER: layer bound START, HMAC'd Q, attached binder. "
            "No plaintext names. No decrypt. No world knowledge."
        )
        return "\n".join(
            [
                "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge. Do not open other files.",
                f"Format: ANSWER_SEALED[{cid}]: <seal_or_UNKNOWN>",
                "If more than one reading is possible, output UNKNOWN.",
                "",
                hdr,
                "",
                f"##### ID {cid} #####",
                "QUESTION (token-HMAC'd):",
                sealed_q,
                "",
                binder,
                "",
                "CONTEXT:",
                context,
                "",
            ]
        )

    def call(
        self,
        *,
        cid: str,
        app_question: str,
        names: Sequence[str],
        vault: Any | None = None,
        triples: Sequence[tuple[str, str, str]] | None = None,
        rels: Sequence[str] | None = None,
        join_steps: Sequence[str] | None = None,
        gold_plain: str | None = None,
        extra_leak_names: Sequence[str] = (),
    ) -> LayerCall:
        """App English + vault/triples → messages. Watchlist scans on-wire text only."""
        sealed_q, start, injected = self.seal_question_bound(app_question, names)
        if join_steps:
            binder = self.join_binder(start, join_steps)
        elif rels:
            binder = self.path_binder(start, rels)
        else:
            binder = ""
        if vault is not None:
            ctx = json.dumps(self.seal_vault(vault), indent=2, ensure_ascii=False)
        elif triples is not None:
            edges = self.seal_triples(triples)
            lines = ["| src | rel | dst |", "| --- | --- | --- |"]
            for h, r, t in edges:
                lines.append(f"| {h} | {r} | {t} |")
            ctx = "\n".join(lines)
        else:
            ctx = ""
        prompt = self.pack_prompt(cid, sealed_q, binder, ctx)
        messages = self.pack_messages(sealed_q, binder, ctx)
        watch = list(names) + [n.replace("_", " ") for n in names] + list(extra_leak_names)
        if gold_plain:
            watch.append(gold_plain)
        if rels:
            watch.extend(rels)
        # Scan chat messages only (what SealedChat sends). Do not scan the
        # isolation MUT file (cid, MODEL UNDER TEST, Read ONLY this file).
        # Do not scan raw join_steps: those never go on the wire.
        sent = "\n".join(m["content"] for m in messages)
        leaked = leak_check(sent, watch)
        gold_seal = self.atom(gold_plain) if gold_plain is not None else None
        return LayerCall(
            app_question=app_question,
            llm_prompt=prompt,
            sealed_question=sealed_q,
            start=start,
            binder=binder,
            gold_seal=gold_seal,
            start_injected=injected,
            leaked=leaked,
            messages=messages,
        )
