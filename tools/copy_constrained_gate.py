#!/usr/bin/env python3
"""
Copy-constrained sealed channel (architecture sketch + enforceable harness filter).

Directional proposal for the paper:
  - Instructions may be cleartext
  - Payload is sealed
  - Model outputs are accepted ONLY if they are exact substrings of the sealed
    context (or UNKNOWN). This is a *harness/decoder constraint*, not a new LLM.

This turns truncation/typo/decoy failure modes into hard rejects and gives a
checkable non-paraphrase property for sealed spans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GateResult:
    accepted: bool
    reason: str
    normalized: str | None


SEAL_TOKEN = re.compile(r"(?:s[0-9a-f]{4}|W[0-9a-f]+|E[0-9a-f]+)")


def extract_answer_sealed(reply: str) -> str | None:
    m = re.search(r"ANSWER_SEALED:\s*(.+)", reply or "", re.I | re.S)
    if not m:
        return None
    return m.group(1).strip()


def gate_copy_only(reply: str, sealed_context: str) -> GateResult:
    """
    Accept iff reply is UNKNOWN or ANSWER_SEALED payload is an exact contiguous
    substring of sealed_context (after whitespace normalize).
    """
    if re.search(r"^\s*UNKNOWN\s*$", reply or "", re.I | re.M) and "ANSWER_SEALED" not in (reply or "").upper():
        return GateResult(True, "unknown_allowed", "UNKNOWN")

    sealed = extract_answer_sealed(reply or "")
    if not sealed:
        return GateResult(False, "missing_answer_sealed", None)

    # normalize spaces
    cand = " ".join(sealed.split())
    ctx = " ".join(sealed_context.split())
    if cand and cand in ctx:
        return GateResult(True, "exact_substring_copy", cand)

    # also allow pure seal-token sequences matching a line value after >>> or |
    if cand in sealed_context:
        return GateResult(True, "raw_substring_copy", cand)

    return GateResult(False, "not_a_copy_of_context", cand)


def demo():
    ctx = "Eaaa | Ebbb | Ec71de67166d8\nExxx | Eyyy | E0c347949830b"
    good = "ANSWER_SEALED: Ec71de67166d8"
    bad = "ANSWER_SEALED: Ec71de67166d9"  # typo
    print(gate_copy_only(good, ctx))
    print(gate_copy_only(bad, ctx))
    print(gate_copy_only("UNKNOWN", ctx))


if __name__ == "__main__":
    demo()
