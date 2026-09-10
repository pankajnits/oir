"""App-side picture: names stay here; LLM would only see the packed prompt.

MiddleLayer.call() only packs. It does not send HTTP.
rels= attaches PATH (H2 control), not the paper's free two-path 6/32 cell.

This script uses SealRouter as a stand-in LLM (engine ceiling). For a public
OpenAI call, see examples/openai_bridge.py. Paper scores are in results/.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from oir.layer import MiddleLayer
except ImportError:  # repo checkout without `pip install -e .`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from oir.layer import MiddleLayer


def main():
    layer = MiddleLayer()  # fresh key every process; use new_call() per request
    person = "Dara Khosrowshahi"
    app_q = f"Which city is the site of the department of {person} in?"
    triples = [
        (person, "in_dept", "Dept_HR"),
        ("Dept_HR", "at_site", "Site_SF"),
        ("Site_SF", "in_city", "San Francisco"),
        ("Other", "in_dept", "Dept_X"),
        ("Dept_X", "at_site", "Site_X"),
        ("Site_X", "in_city", "Austin"),
    ]
    call = layer.call(
        cid="APP_0",
        app_question=app_q,
        names=[person],
        triples=triples,
        rels=["in_dept", "at_site", "in_city"],
        gold_plain="San Francisco",
    )
    print("APP sees:", app_q)
    print("LLM question:", call.sealed_question)
    print("Watched names on the wire (messages):", call.leaked or "none")
    # Fake an LLM that copies the engine gold (the paper's SealRouter ceiling).
    llm_answer = layer.execute_path(triples, person, ["in_dept", "at_site", "in_city"])[0]
    print("LLM would return:", llm_answer)
    print("APP decodes:", layer.unseal(llm_answer))


if __name__ == "__main__":
    main()
