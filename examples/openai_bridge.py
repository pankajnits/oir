"""App → OIR layer packs → OpenAI-compatible LLM → app plaintext.

rels= attaches PATH (H2). Product HMAC's names and relations and answers
ANSWER_SEALED. That is not the paper free two-path cell (OpenAI 6/32).

Requires OPENAI_API_KEY and: pip install 'oir-layer[openai]'
Default model is gpt-4o-mini (product). Paper isolation cells use gpt-5.6-sol.

    python3 examples/openai_bridge.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from oir import MiddleLayer, SealedChat
    from oir.chat import OpenAIChatClient
except ImportError:  # repo checkout without `pip install -e .`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from oir import MiddleLayer, SealedChat
    from oir.chat import OpenAIChatClient


PERSON = "Dara Khosrowshahi"
TRIPLES = [
    (PERSON, "in_dept", "Dept_HR"),
    ("Dept_HR", "at_site", "Site_SF"),
    ("Site_SF", "in_city", "San Francisco"),
    ("Other", "in_dept", "Dept_X"),
    ("Dept_X", "at_site", "Site_X"),
    ("Site_X", "in_city", "Austin"),
]
RELS = ["in_dept", "at_site", "in_city"]


def main():
    layer = MiddleLayer()  # rotate: MiddleLayer() per request
    if not os.environ.get("OPENAI_API_KEY"):
        gold = layer.execute_path(TRIPLES, PERSON, RELS)[0]
        print("No OPENAI_API_KEY. Engine ceiling (not an LLM):", layer.unseal(gold))
        print("Set OPENAI_API_KEY and pip install 'oir-layer[openai]' to call gpt-4o-mini.")
        return
    chat = SealedChat(layer, OpenAIChatClient(model=os.environ.get("OIR_MODEL", "gpt-4o-mini")))
    q = f"Which city is the site of the department of {PERSON} in?"
    print("APP:", q)
    print("APP decoded:", chat.ask(q, names=[PERSON], triples=TRIPLES, rels=RELS, extra_leak_names=["San Francisco", "Austin"]))


if __name__ == "__main__":
    main()
