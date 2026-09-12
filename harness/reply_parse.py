"""Shared reply parsing for the isolation runners (OpenAI and agent bridge).

Review fix: an empty completion is recorded as ``NO_OUTPUT``, never as
``UNKNOWN``. The previous per-runner ``parse`` let an empty reply fall through
to ``UNKNOWN`` and wrote ``ANSWER_*[id]: UNKNOWN``; the resume logic then
treated that file as final, so an exhausted token budget became a permanent,
indistinguishable "abstention". Non-empty replies parse exactly as before.
"""
from __future__ import annotations

import re

_MARK = re.compile(r"(?:\*{1,3}|`)+")


def clean_pred(pred: str) -> str:
    """Strip wrapping markdown so ``Burbank**`` and ``** Amsterdam`` score as cities."""
    p = (pred or "").strip()
    if not p:
        return p
    p = re.sub(rf"^{_MARK.pattern}\s*", "", p)
    p = re.sub(rf"\s*{_MARK.pattern}$", "", p)
    return p.strip()


NO_OUTPUT = "NO_OUTPUT"
ANS_SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(?:\*+|`+)*\s*(\S+)", re.I)
ANS_PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(?:\*+|`+)*\s*([^\n]+)", re.I)
_REPLY = re.compile(r"^ANSWER_(?:PLAIN|SEALED)\[[^\]]+\]: (\S+)\n# (raw_tail|raw)\n(.*)$", re.S)


def parse(cid: str, raw: str, *, sealed: bool) -> tuple[str, str]:
    """Return ``(pred, reply_file_text)`` for one model reply."""
    rx = ANS_SEAL if sealed else ANS_PLAIN
    prefix = "ANSWER_SEALED" if sealed else "ANSWER_PLAIN"
    if not raw.strip():
        return NO_OUTPUT, f"{prefix}[{cid}]: {NO_OUTPUT}\n# raw\n"
    ms = list(rx.finditer(raw))
    if ms:
        pred = clean_pred(ms[-1].group(2).strip())
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
        pred = clean_pred(lines[-1].split()[-1].strip(".,;:"))
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
    pred = clean_pred(pred)
    if pred.upper() == NO_OUTPUT:
        return "no_output"
    if kind == "raw" and not body.strip():
        return "legacy_empty"
    if kind == "raw":
        return "fallback_parse"
    return "explicit_unknown" if pred.upper() == "UNKNOWN" else "explicit_answer"


def preds_from_text(text: str, rx: re.Pattern[str]) -> dict[str, str]:
    """Last well-formed ANSWER token per id; wrapping markdown is stripped."""
    out: dict[str, str] = {}
    for m in rx.finditer(text or ""):
        tok = clean_pred(m.group(2).strip())
        if tok and tok.strip("*`"):
            out[m.group(1)] = tok
    return out


def transcript_kind(text: str) -> str:
    """How much of the model reply was stored with the scored answer line.

    ``transcript`` is the current runner (``# raw_tail`` then a newline).
    ``short_tail`` is a one-line ``# raw_tail ...`` note, not a dump.
    ``induce`` is the sealed-demo helper, not a free completion.
    ``answer_only`` is the scored line with no tail.
    """
    t = text or ""
    if "induce_mut" in t or "method=sealed_demo" in t:
        return "induce"
    if "# raw_tail\n" in t or "\n# raw\n" in t or t.startswith("# raw\n"):
        return "transcript"
    if "# raw_tail" in t:
        return "short_tail"
    return "answer_only"


def first_pred(text: str) -> str:
    """Prediction on the first line of a stored reply ('' if none)."""
    if not text or text.startswith("ERROR"):
        return ""
    head = text.splitlines()[0]
    return clean_pred(head.split("]:", 1)[1]) if "]:" in head else ""


def is_final(text: str) -> bool:
    """True if a stored reply should be skipped on resume.

    ``no_output`` is never final. ``legacy_empty`` stays final so that resuming
    does not silently overwrite locked reply files; runners expose
    ``--retry-empty`` to re-query those explicitly. ``ERROR:`` in a raw tail
    does not make a well-formed answer line retryable (``classify`` only treats
    files that start with ``ERROR`` as errors).
    """
    if classify(text) in {"error", "no_output"}:
        return False
    if not (ANS_SEAL.search(text) or ANS_PLAIN.search(text)):
        return False
    return True
