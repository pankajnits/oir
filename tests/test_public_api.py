"""Public package surface — imports a developer would copy from the README."""
from __future__ import annotations

import oir
import pytest
from oir import EntitySeal, LeakError, MiddleLayer, SealedChat, SealRouter
from oir.chat import parse_sealed_answer


def test_version_and_all():
    assert oir.__version__ == "0.1.0"
    for name in (
        "MiddleLayer",
        "SealedChat",
        "LeakError",
        "EntitySeal",
        "SealRouter",
        "OpenAIChatClient",
        "ChatCompleter",
    ):
        assert name in oir.__all__
        assert getattr(oir, name)


def test_seal_router_path():
    r = SealRouter([("A", "r1", "B"), ("B", "r2", "C")])
    assert r.path("A", ["r1", "r2"]) == ["C"]
    assert r.lookup("A", "missing") == []


def test_entity_seal_normalize_equality():
    s = EntitySeal(b"k" * 16)
    assert s.atom("Bob Iger") == s.atom("Bob_Iger")
    assert s.rev[s.atom("Bob Iger")] == "Bob_Iger"
    assert s.normalize("北京") == "北京"
    assert s.normalize("李小龙") != "EMPTY"
    tok = s.atom("Bob Iger")
    assert s.is_hmac_atom(tok)
    assert not s.is_hmac_atom("Employer")
    assert not s.is_hmac_atom("Edmond T. Greville")
    EntitySeal.assert_raw_injective(["works_at", "headquartered_in"])
    EntitySeal.assert_raw_injective(["Bob Iger", "Bob_Iger"])  # whitespace fold matches atom()
    with pytest.raises(ValueError, match="normalize collision"):
        EntitySeal.assert_raw_injective(["東京 Tower", "大阪 Tower"])
    t = s.atom("works_at")
    s.fwd.clear()
    s.rev[t] = "other"
    try:
        s.atom("works_at")
    except ValueError as e:
        assert "HMAC collision" in str(e)
    else:
        raise AssertionError("expected HMAC collision")


def test_messages_are_not_mut_files():
    layer = MiddleLayer(b"msg-test-key-16b")
    call = layer.call(
        cid="X",
        app_question="Where is Steve Weed?",
        names=["Steve Weed"],
    )
    blob = "\n".join(m["content"] for m in call.messages)
    assert "MODEL UNDER TEST" not in blob
    assert "##### ID" not in blob
    assert "MODEL UNDER TEST" in call.llm_prompt
    assert "##### ID X #####" in call.llm_prompt
    layer = MiddleLayer(b"msg-test-key-16b")
    call = layer.call(
        cid="X",
        app_question="Where is Steve Weed?",
        names=["Steve Weed"],
        triples=[("Steve Weed", "in_city", "Dallas")],
        rels=["in_city"],
    )
    blob = "\n".join(m["content"] for m in call.messages)
    assert "MODEL UNDER TEST" not in blob
    assert "Steve" not in blob
    assert call.messages[0]["role"] == "system"
    assert "MODEL UNDER TEST" in call.llm_prompt
    assert "##### ID X #####" in call.llm_prompt


def test_unknown_parse_and_sealed_chat_unknown():
    assert parse_sealed_answer("I cannot tell UNKNOWN here") == "UNKNOWN"

    class U:
        def complete(self, messages):
            return "ANSWER_SEALED: UNKNOWN"

    chat = SealedChat(MiddleLayer(b"unk-test-key-16bb"), U())
    assert chat.ask("Where is Steve Weed?", names=["Steve Weed"]) is None


def test_leak_error_is_exported():
    assert issubclass(LeakError, RuntimeError)


def test_tools_seal_router_shim():
    """Paper harnesses still import SealRouter from tools/."""
    import sys
    from pathlib import Path

    tools = str(Path(__file__).resolve().parents[1] / "tools")
    sys.path.insert(0, tools)
    try:
        import seal_router

        r = seal_router.SealRouter([("A", "r1", "B"), ("B", "r2", "C")])
        assert r.path("A", ["r1", "r2"]) == ["C"]
        assert r.step("A", "r1") == ["B"]
    finally:
        sys.path.remove(tools)
