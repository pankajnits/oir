"""Unit tests for oir.layer — lexicon hiding + roundtrip, no LLM."""
from __future__ import annotations

from oir.layer import MiddleLayer


def test_pii_stays_home_and_engine_joins():
    layer = MiddleLayer(b"unit-test-key-16!")
    person, city = "Samuel W Fordyce", "Dallas"
    app_q = f"Which city is the site of the department of {person} in?"
    triples = [
        (person, "in_dept", "Dept_0"),
        ("Dept_0", "at_site", "Site_0"),
        ("Site_0", "in_city", city),
        ("Other Person", "in_dept", "Dept_1"),
        ("Dept_1", "at_site", "Site_1"),
        ("Site_1", "in_city", "Austin"),
    ]
    call = layer.call(
        cid="T0",
        app_question=app_q,
        names=[person],
        triples=triples,
        rels=["in_dept", "at_site", "in_city"],
        gold_plain=city,
        extra_leak_names=["Acme", "Austin", "Other Person"],
    )
    assert call.leaked == []
    assert "Samuel" not in call.llm_prompt
    assert "Fordyce" not in call.llm_prompt
    assert "Dallas" not in call.llm_prompt
    assert "What" not in call.sealed_question and "Which" not in call.sealed_question
    assert call.start in call.sealed_question
    assert layer.nobind_question(app_q).count(call.start) == 0
    got = layer.execute_path(triples, person, ["in_dept", "at_site", "in_city"])
    assert got == [call.gold_seal]
    assert layer.unseal(got[0]) == city


def test_per_call_keys_unlink():
    a, b = MiddleLayer(), MiddleLayer()
    assert a.atom("Steve Weed") != b.atom("Steve Weed")
    assert a.unseal(b.atom("Steve Weed")) is None


def test_start_injected_when_span_misses():
    layer = MiddleLayer(b"inject-key-16byte")
    q, start, injected = layer.seal_question_bound(
        "When did John V, Prince Of Anhalt-Zerbst's father die?",
        ["John V of Anhalt-Zerbst"],
    )
    assert injected
    assert start in q


def test_equality_inside_one_call():
    layer = MiddleLayer(b"same-call-key!!!!")
    assert layer.atom("Steve Weed") == layer.atom("Steve_Weed")
    assert layer.atom("Steve Weed") == layer.bind_name("Steve Weed")


def test_new_call_unlinks_keys():
    a = MiddleLayer(b"parent-key-16byt")
    b = a.new_call()
    assert a.atom("Steve Weed") != b.atom("Steve Weed")
    assert a.unseal(b.atom("Steve Weed")) is None


def test_vault_json_has_no_plaintext_names():
    layer = MiddleLayer(b"vault-test-key16b")
    person = "Samuel W Fordyce"
    call = layer.call(
        cid="V0",
        app_question=f"Where does {person} work?",
        names=[person],
        vault={"employee": person, "city": "Dallas"},
        extra_leak_names=["Dallas"],
    )
    blob = "\n".join(m["content"] for m in call.messages)
    assert "Samuel" not in blob
    assert "Dallas" not in blob
    assert "Fordyce" not in blob


def test_join_steps_are_hmac_not_plaintext():
    layer = MiddleLayer(b"join-seal-key16bb")
    call = layer.call(
        cid="J0",
        app_question="Where is Steve Weed?",
        names=["Steve Weed"],
        join_steps=["LOOKUP Dept then Dallas"],
        gold_plain="Dallas",
        extra_leak_names=["Dallas"],
    )
    blob = "\n".join(m["content"] for m in call.messages)
    assert "Dallas" not in blob
    assert "LOOKUP" not in blob
    assert call.leaked == []
    assert "Dallas" not in call.llm_prompt


def test_leak_check_does_not_match_ann_in_answer():
    from oir.layer import leak_check

    assert leak_check("ANSWER_SEALED: UNKNOWN", ["Ann"]) == []
    assert leak_check("Return Dallas now", ["Dallas"]) == ["Dallas"]


def test_cjk_name_is_hmac_not_empty():
    layer = MiddleLayer(b"cjk-test-key-16bb")
    name = "北京"
    call = layer.call(
        cid="C0",
        app_question=f"Where is {name}?",
        names=[name],
        extra_leak_names=[name],
    )
    blob = "\n".join(m["content"] for m in call.messages)
    assert name not in blob
    assert name not in call.llm_prompt
    assert call.leaked == []
    assert layer.unseal(call.start) == name
    assert layer.atom(name) != layer.atom("EMPTY")
    assert layer.unseal(layer.atom("李小龙")) == "李小龙"


def test_rel_starting_with_e_is_hmac_not_left_english():
    layer = MiddleLayer(b"employer-rel-key!")
    person = "Steve Weed"
    call = layer.call(
        cid="E0",
        app_question=f"Where does {person} work?",
        names=[person],
        triples=[(person, "Employer", "Dallas")],
        rels=["Employer"],
        extra_leak_names=["Dallas"],
    )
    blob = "\n".join(m["content"] for m in call.messages)
    assert "Employer" not in blob
    assert "Employer" not in call.llm_prompt
    assert call.leaked == []
    sealed = layer.atom("Employer")
    assert sealed in blob
    already = layer.path_binder(call.start, [sealed])
    assert sealed in already
    assert layer.atom("Employer") == sealed


def test_bind_span_does_not_eat_prefix_of_later_word():
    from oir.layer import bind_span

    q, _ = bind_span("Where is Al also based?", "Al", "ESTART")
    assert q == "Where is ESTART also based?"
    q2, _ = bind_span("Anniversary for Ann", "Ann", "ESTART")
    assert q2 == "Anniversary for ESTART"


def test_bind_span_and_leak_check_use_unicode_word_boundaries():
    from oir.layer import bind_span, leak_check

    # ASCII class (?<![A-Za-z0-9_]) treats 李 as a boundary and would bind 小龙
    # inside 李小龙. Unicode \\w does not.
    q, injected = bind_span("Where is 李小龙 based?", "小龙", "ESTART")
    assert "李小龙" in q
    assert "李ESTART" not in q
    assert injected
    assert leak_check("李小龙 starred", ["小龙"]) == []
    assert leak_check("李小龙 starred", ["李小龙"]) == ["李小龙"]


def test_join_binder_english_start_with_e_is_hmac():
    layer = MiddleLayer(b"edmond-start-key!")
    body = layer.join_binder("Edmond T. Greville", ["take city"])
    assert "Edmond" not in body
    assert "Greville" not in body
    assert layer.sealer.is_hmac_atom(body.split("START ", 1)[1].split("\n", 1)[0])
