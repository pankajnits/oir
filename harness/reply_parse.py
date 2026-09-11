"""Shared reply parsing for the isolation runners (OpenAI and agent bridge).

Review fix: an empty completion is recorded as ``NO_OUTPUT``, never as
``UNKNOWN``. The previous per-runner ``parse`` let an empty reply fall through
to ``UNKNOWN`` and wrote ``ANSWER_*[id]: UNKNOWN``; the resume logic then
treated that file as final, so an exhausted token budget became a permanent,
indistinguishable "abstention". Non-empty replies parse exactly as before.
"""
from __future__ import annotations

import re

NO_OUTPUT = "NO_OUTPUT"
ANS_SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
ANS_PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*([^\n]+)", re.I)
_REPLY = re.compile(r"^ANSWER_(?:PLAIN|SEALED)\[[^\]]+\]: (\S+)\n# (raw_tail|raw)\n(.*)$", re.S)


def parse(cid: str, raw: str, *, sealed: bool) -> tuple[str, str]:
    """Return ``(pred, reply_file_text)`` for one model reply."""
    rx = ANS_SEAL if sealed else ANS_PLAIN
    prefix = "ANSWER_SEALED" if sealed else "ANSWER_PLAIN"
    if not raw.strip():
        return NO_OUTPUT, f"{prefix}[{cid}]: {NO_OUTPUT}\n# raw\n"
    ms = list(rx.finditer(raw))
    if ms:
        pred = ms[-1].group(2).strip()
        return pred, f"{prefix}[{cid}]: {pred}\n# raw_tail\n{raw[-800:]}\n"
    if sealed:
        atom = re.search(r"\b(E[0-9a-f]{12})\b", raw, re.I)
        if atom and "ERROR:" not in raw:
            pred = atom.group(1)
            return pred, f"{prefix}[{cid}]: {pred}\n# raw\n{raw[:2500]}\n"
    if re.search(r"\bUNKNOWN\b", raw, re.I) and "ERROR:" not in raw:
        return "UNKNOWN", f"{prefix}[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.startswith("#")]
    if lines and "ERROR:" not in raw:
        pred = lines[-1].split()[-1].strip(".,;:")
        return pred, f"{prefix}[{cid}]: {pred}\n# raw\n{raw[:2500]}\n"
    return "UNKNOWN", f"{prefix}[{cid}]: UNKNOWN\n# raw\n{raw[:2500]}\n"


def classify(text: str) -> str:
    """Outcome class of a stored reply file.

    ``legacy_empty`` marks files written by the old runners from an empty
    completion (``ANSWER_*: UNKNOWN`` followed by an empty ``# raw`` block).
    """
    if not text or text.startswith("ERROR"):
        return "error"
    m = _REPLY.match(text)
    if not m:
        return "other_format"
    pred, kind, body = m.groups()
    if pred.upper() == NO_OUTPUT:
        return "no_output"
    if kind == "raw" and not body.strip():
        return "legacy_empty"
    if kind == "raw":
        return "fallback_parse"
    return "explicit_unknown" if pred.upper() == "UNKNOWN" else "explicit_answer"


def first_pred(text: str) -> str:
    """Prediction on the first line of a stored reply ('' if none)."""
    if not text or text.startswith("ERROR"):
        return ""
    head = text.splitlines()[0]
    return head.split("]:", 1)[1].strip() if "]:" in head else ""


def is_final(text: str) -> bool:
    """True if a stored reply should be skipped on resume.

    ``no_output`` is never final. ``legacy_empty`` stays final so that resuming
    does not silently overwrite locked reply files; runners expose
    ``--retry-empty`` to re-query those explicitly.
    """
    if not text or "ERROR:" in text:
        return False
    if not (ANS_SEAL.search(text) or ANS_PLAIN.search(text)):
        return False
    return classify(text) != "no_output"
