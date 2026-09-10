#!/usr/bin/env python3
"""HR-style app using ``oir.MiddleLayer`` as middleware.

No network. A SealRouter-backed completer stands in for the remote LLM so the
example is CI-safe and clone-and-run. Names stay in the app; the fake LLM only
sees HMAC atoms. This is lexicon hiding, not confidentiality.
rels= attaches PATH (paper H2), not the free two-path OpenAI 6/32 cell.

    python3 examples/middleware_hr.py

The same packing is what ``SealedChat`` sends to OpenAI
(``examples/openai_bridge.py``).
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from oir import MiddleLayer, SealedChat, SealRouter
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from oir import MiddleLayer, SealedChat, SealRouter


PERSON = "Dara Khosrowshahi"
GOLD = "San Francisco"
DECOY = "Austin"
TRIPLES = [
    (PERSON, "in_dept", "Dept_HR"),
    ("Dept_HR", "at_site", "Site_SF"),
    ("Site_SF", "in_city", GOLD),
    ("Other", "in_dept", "Dept_X"),
    ("Dept_X", "at_site", "Site_X"),
    ("Site_X", "in_city", DECOY),
]
RELS = ["in_dept", "at_site", "in_city"]
WATCH = [PERSON, GOLD, DECOY, "Dara", "Khosrowshahi"]


class RouterCompleter:
    """Deterministic stand-in for a chat-completion API.

    Reads the sealed PATH binder and CONTEXT table the layer packed, executes
    ``SealRouter``, returns ``ANSWER_SEALED``. Refuses if a watched name is on the wire.
    """

    def complete(self, messages: list[dict[str, str]]) -> str:
        blob = "\n".join(m["content"] for m in messages)
        for name in WATCH:
            if name in blob:
                raise AssertionError(f"plaintext leaked into LLM payload: {name!r}")
        start, rels, triples = _parse_sealed_path(blob)
        tails = SealRouter(triples).path(start, rels)
        if len(tails) != 1:
            return "ANSWER_SEALED: UNKNOWN"
        return f"ANSWER_SEALED: {tails[0]}"


def _parse_sealed_path(blob: str) -> tuple[str, list[str], list[tuple[str, str, str]]]:
    start = None
    rels: list[str] = []
    triples: list[tuple[str, str, str]] = []
    in_ctx = False
    for raw in blob.splitlines():
        line = raw.strip()
        if line.startswith("START "):
            start = line.split(None, 1)[1]
        elif line[:1] == "R" and len(line) > 1 and line[1].isdigit():
            rels.append(line.split(None, 1)[1])
        elif line == "CONTEXT:":
            in_ctx = True
        elif in_ctx and line.startswith("|") and "src" not in line and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 3:
                triples.append((cells[0], cells[1], cells[2]))
    if not start or not rels or not triples:
        raise ValueError("packed prompt missing PATH or CONTEXT")
    return start, rels, triples


def run() -> dict:
    q = f"Which city is the site of the department of {PERSON} in?"
    layer = MiddleLayer()
    chat = SealedChat(layer, RouterCompleter())

    call = chat.prepare(
        q,
        names=[PERSON],
        triples=TRIPLES,
        rels=RELS,
        extra_leak_names=[GOLD, DECOY],
    )
    assert call.leaked == []
    assert call.start in call.sealed_question
    assert PERSON not in "\n".join(m["content"] for m in call.messages)
    assert GOLD not in "\n".join(m["content"] for m in call.messages)

    city = chat.ask(
        q,
        names=[PERSON],
        triples=TRIPLES,
        rels=RELS,
        extra_leak_names=[GOLD, DECOY],
    )
    nobind = layer.nobind_question(q)
    start_in_nobind = call.start in nobind

    join_call = chat.prepare(
        q,
        names=[PERSON],
        join_steps=[f"Return {GOLD}"],
        extra_leak_names=[GOLD],
    )
    join_blob = "\n".join(m["content"] for m in join_call.messages)
    join_hmac_hides_gold = join_call.leaked == [] and GOLD not in join_blob

    return {
        "app_question": q,
        "decoded": city,
        "engine_ok": city == GOLD,
        "start_bound": True,
        "nobind_misses_start": not start_in_nobind,
        "join_hmac_hides_gold": join_hmac_hides_gold,
        "per_call_keys_differ": layer.atom(PERSON) != layer.new_call().atom(PERSON),
    }


def main() -> None:
    out = run()
    for k, v in out.items():
        if k == "app_question":
            print("APP:", v)
        else:
            print(f"{k}: {v}")
    if not (
        out["engine_ok"]
        and out["nobind_misses_start"]
        and out["join_hmac_hides_gold"]
        and out["per_call_keys_differ"]
    ):
        raise SystemExit("middleware example failed")
    print("ok")


if __name__ == "__main__":
    main()
