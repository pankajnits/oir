"""Tests for the OpenAI-shaped chat bridge (no network)."""
from __future__ import annotations

import pytest
from oir.chat import SealedChat, parse_sealed_answer
from oir.errors import LeakError
from oir.layer import MiddleLayer


class FakeLLM:
    def __init__(self, layer: MiddleLayer, triples, start, rels):
        self.gold = layer.execute_path(triples, start, rels)[0]

    def complete(self, messages):
        blob = "\n".join(m["content"] for m in messages)
        assert "Dara" not in blob
        assert "Khosrowshahi" not in blob
        assert "San Francisco" not in blob
        return f"ANSWER_SEALED: {self.gold}"


def _world():
    person = "Dara Khosrowshahi"
    triples = [
        (person, "in_dept", "Dept_HR"),
        ("Dept_HR", "at_site", "Site_SF"),
        ("Site_SF", "in_city", "San Francisco"),
        ("Other", "in_dept", "Dept_X"),
        ("Dept_X", "at_site", "Site_X"),
        ("Site_X", "in_city", "Austin"),
    ]
    rels = ["in_dept", "at_site", "in_city"]
    return person, triples, rels


def test_sealed_chat_roundtrip_with_fake_openai():
    layer = MiddleLayer(b"chat-test-key-16b")
    person, triples, rels = _world()
    chat = SealedChat(layer, FakeLLM(layer, triples, person, rels))
    got = chat.ask(
        f"Which city is the site of the department of {person} in?",
        names=[person],
        triples=triples,
        rels=rels,
        extra_leak_names=["San Francisco", "Austin"],
    )
    assert got == "San Francisco"


def test_ask_does_not_rotate_layer_key():
    layer = MiddleLayer(b"chat-test-key-16b")
    before = layer.atom("probe-atom")
    person, triples, rels = _world()
    chat = SealedChat(layer, FakeLLM(layer, triples, person, rels))
    chat.ask(
        f"Which city is the site of the department of {person} in?",
        names=[person],
        triples=triples,
        rels=rels,
        extra_leak_names=["San Francisco", "Austin"],
    )
    assert layer.atom("probe-atom") == before


def test_parse_sealed_answer():
    assert parse_sealed_answer("ANSWER_SEALED[X]: Eabc") == "Eabc"
    assert parse_sealed_answer("ANSWER_SEALED: UNKNOWN") == "UNKNOWN"


def test_join_steps_gold_is_hmac_not_a_false_leak():
    layer = MiddleLayer(b"leak-test-key-16c")

    class Boom:
        def complete(self, messages):
            raise AssertionError("must not call LLM")

    chat = SealedChat(layer, Boom())
    call = chat.prepare(
        "Where is Steve Weed?",
        names=["Steve Weed"],
        join_steps=["Return Dallas"],
        extra_leak_names=["Dallas"],
    )
    blob = "\n".join(m["content"] for m in call.messages)
    assert call.leaked == []
    assert "Dallas" not in blob


def test_header_only_cid_is_not_a_wire_leak():
    """MUT isolation header can name cid; SealedChat sends messages only."""
    layer = MiddleLayer(b"leak-test-key-16c")

    class Boom:
        def complete(self, messages):
            raise AssertionError("must not call LLM")

    chat = SealedChat(layer, Boom())
    call = chat.prepare(
        "Where is Steve Weed?",
        names=["Steve Weed"],
        cid="Dallas",
        extra_leak_names=["Dallas"],
    )
    blob = "\n".join(m["content"] for m in call.messages)
    assert call.leaked == []
    assert "Dallas" not in blob
    assert "Dallas" in call.llm_prompt


def test_leak_refuses_when_watched_token_is_in_messages():
    layer = MiddleLayer(b"leak-msg-key-16bb")
    person, triples, rels = _world()

    class Boom:
        def complete(self, messages):
            raise AssertionError("must not call LLM")

    chat = SealedChat(layer, Boom())
    with pytest.raises(LeakError) as ei:
        chat.prepare(
            f"Which city is the site of the department of {person} in?",
            names=[person],
            triples=triples,
            rels=rels,
            extra_leak_names=["PATH_QUERY"],
        )
    assert "PATH_QUERY" in ei.value.names


def test_pretty_false_keeps_underscore():
    layer = MiddleLayer(b"chat-test-key-16b")
    person, triples, rels = _world()
    chat = SealedChat(layer, FakeLLM(layer, triples, person, rels))
    got = chat.ask(
        f"Which city is the site of the department of {person} in?",
        names=[person],
        triples=triples,
        rels=rels,
        extra_leak_names=["San Francisco", "Austin"],
        pretty=False,
    )
    assert got == "San_Francisco"


def test_openai_import_error_mentions_extra(monkeypatch):
    import builtins
    import sys

    import oir.chat as chat_mod

    real = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "openai" or name.startswith("openai."):
            raise ImportError("simulated missing extra")
        return real(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "openai", raising=False)
    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(ImportError, match=r"oir-layer\[openai\]"):
        chat_mod.OpenAIChatClient()


def test_openai_gpt5_omits_temperature(monkeypatch):
    import sys
    import types

    import oir.chat as chat_mod

    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            if "temperature" in kwargs:
                raise RuntimeError(
                    "Unsupported value: 'temperature' does not support 0 with this model."
                )

            class Msg:
                content = "ANSWER_SEALED: UNKNOWN"

            class Choice:
                message = Msg()

            class Resp:
                choices = [Choice()]

            return Resp()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    fake = types.ModuleType("openai")
    fake.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake)
    client = chat_mod.OpenAIChatClient(api_key="x", model="gpt-5.6-sol")
    assert client.complete([{"role": "user", "content": "hi"}]) == "ANSWER_SEALED: UNKNOWN"
    assert len(calls) == 1
    assert "temperature" not in calls[0]
    assert calls[0]["max_completion_tokens"] == 512


def test_openai_mini_sends_temperature(monkeypatch):
    import sys
    import types

    import oir.chat as chat_mod

    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(dict(kwargs))

            class Msg:
                content = "ANSWER_SEALED: UNKNOWN"

            class Choice:
                message = Msg()

            class Resp:
                choices = [Choice()]

            return Resp()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    fake = types.ModuleType("openai")
    fake.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake)
    client = chat_mod.OpenAIChatClient(api_key="x", model="gpt-4o-mini")
    assert client.complete([{"role": "user", "content": "hi"}]) == "ANSWER_SEALED: UNKNOWN"
    assert calls[0]["temperature"] == 0
    assert "max_completion_tokens" not in calls[0]
