"""Chat bridge: app → MiddleLayer → public LLM (OpenAI-compatible) → unseal.

Watched name strings are HMAC'd before send. That is lexicon hiding, not
confidentiality: equality is preserved, ``leak_check`` is a watchlist on
``call.messages`` (not the isolation MUT file ``llm_prompt``), and the layer
holds the key. Isolation quizzes in ``runs/`` are the paper measurement; this
adapter is the product-shaped API.

    class Echo:
        def complete(self, messages):
            return "ANSWER_SEALED: UNKNOWN"

    from oir import MiddleLayer
    from oir.chat import SealedChat

    chat = SealedChat(MiddleLayer(), Echo())
    chat.ask("Where is Steve Weed?", names=["Steve Weed"])  # None

Send ``call.messages`` / ``pack_messages()``, never ``llm_prompt`` / ``pack_mut_batch``.
Without the ``openai`` extra, pass any object with ``complete(messages) -> str``.
"""
from __future__ import annotations

import os
import re
from collections.abc import Sequence
from typing import Any, Protocol

from .errors import LeakError
from .layer import LayerCall, MiddleLayer

__all__ = [
    "ChatCompleter",
    "LeakError",
    "OpenAIChatClient",
    "SealedChat",
    "parse_sealed_answer",
]

SEAL_LINE = re.compile(r"ANSWER_SEALED(?:\[[^\]]+\])?:\s*(\S+)", re.I)


class ChatCompleter(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


class OpenAIChatClient:
    """Thin wrapper around the official OpenAI SDK (optional extra).

    Paper isolation cells use ``gpt-5.6-sol`` with no temperature and
    ``max_completion_tokens=512``. Product defaults remain ``gpt-4o-mini``
    at temperature 0; ``gpt-5*`` product calls use ``max_completion_tokens=4096``
    unless overridden. If a model rejects temperature, it is omitted and retried.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        *,
        timeout: float = 60.0,
        temperature: float | None = 0,
        max_completion_tokens: int | None = None,
    ):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "OpenAI SDK not installed. Run: pip install 'oir-layer[openai]' "
                "or pass any object with complete(messages) -> str"
            ) from e
        self.model = model
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            timeout=timeout,
        )

    def _paper_style(self) -> bool:
        return self.model.startswith(("gpt-5", "o3", "o4"))

    def complete(self, messages: list[dict[str, str]]) -> str:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if self._paper_style():
            kwargs["max_completion_tokens"] = (
                4096 if self.max_completion_tokens is None else self.max_completion_tokens
            )
        elif self.max_completion_tokens is not None:
            kwargs["max_tokens"] = self.max_completion_tokens
        if self.temperature is not None and not self._paper_style():
            kwargs["temperature"] = self.temperature
        try:
            r = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            err = str(e).lower()
            if "temperature" in kwargs and "temperature" in err and "unsupported" in err:
                kwargs.pop("temperature", None)
                r = self.client.chat.completions.create(**kwargs)
            else:
                raise
        return (r.choices[0].message.content or "").strip()


def parse_sealed_answer(text: str, *, prefix: str = "E", nbytes: int = 6) -> str:
    m = SEAL_LINE.search(text)
    if m:
        return m.group(1).strip()
    nhex = nbytes * 2
    atom = re.compile(rf"\b({re.escape(prefix)}[0-9a-f]{{{nhex}}})\b", re.I)
    m = atom.search(text)
    if m:
        return m.group(1)
    if re.search(r"\bUNKNOWN\b", text, re.I):
        return "UNKNOWN"
    raise ValueError(f"no sealed answer in model text: {text[:200]!r}")


class SealedChat:
    """One-shot ask: seal → remote complete → unseal.

    Construct a new ``MiddleLayer()`` per request so yesterday's seals do not match.
    ``ask`` does not rotate the key.
    """

    def __init__(self, layer: MiddleLayer, completer: ChatCompleter):
        self.layer = layer
        self.completer = completer

    def prepare(
        self,
        question: str,
        *,
        names: Sequence[str],
        triples: Sequence[tuple[str, str, str]] | None = None,
        vault: Any = None,
        rels: Sequence[str] | None = None,
        join_steps: Sequence[str] | None = None,
        extra_leak_names: Sequence[str] = (),
        cid: str = "APP",
    ) -> LayerCall:
        call = self.layer.call(
            cid=cid,
            app_question=question,
            names=names,
            triples=triples,
            vault=vault,
            rels=rels,
            join_steps=join_steps,
            extra_leak_names=extra_leak_names,
        )
        if call.leaked:
            raise LeakError(call.leaked)
        return call

    def messages(self, call: LayerCall) -> list[dict[str, str]]:
        return list(call.messages)

    def ask(
        self,
        question: str,
        *,
        names: Sequence[str],
        triples: Sequence[tuple[str, str, str]] | None = None,
        vault: Any = None,
        rels: Sequence[str] | None = None,
        join_steps: Sequence[str] | None = None,
        extra_leak_names: Sequence[str] = (),
        pretty: bool = True,
    ) -> str | None:
        call = self.prepare(
            question,
            names=names,
            triples=triples,
            vault=vault,
            rels=rels,
            join_steps=join_steps,
            extra_leak_names=extra_leak_names,
        )
        raw = self.completer.complete(self.messages(call))
        token = parse_sealed_answer(
            raw, prefix=self.layer.sealer.prefix, nbytes=self.layer.sealer.nbytes
        )
        if token.upper() == "UNKNOWN":
            return None
        plain = self.layer.unseal(token)
        if pretty and plain:
            return plain.replace("_", " ")
        return plain
