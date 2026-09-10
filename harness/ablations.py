#!/usr/bin/env python3
"""
OIR Phase-1 ablation harness.

Builds crack / align / mismatch / confound payloads for a fixed fact set,
varying encoding × boundary protocol.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import re
import string
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "phase1"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

KEY_A = b"oir-phd-phase1-key-A"
KEY_B = b"oir-phd-phase1-key-B"

FACTS = {
    "contingency_code_phrase": "amber lattice seven",
    "decoy_phrase": "crimson willow four",
    "vault_combination": "19-47-82",
    "authorized_opener": "Dr Elias Vorn",
    "specimen_catalog": "NG-4417-BETA",
}
QUERY_KEY = "contingency_code_phrase"
EXPECTED = FACTS[QUERY_KEY]


# -------------------- sealers --------------------

class MonoSealer:
    """Crackable monoalphabetic bijection (confound baseline)."""

    def __init__(self, seed: int = 20260724):
        rng = random.Random(seed)
        src = list(string.ascii_lowercase)
        dst = list(string.ascii_lowercase)
        rng.shuffle(dst)
        lower = dict(zip(src, dst))
        upper = {k.upper(): v.upper() for k, v in lower.items()}
        self.table = {**lower, **upper}
        self.inv = {v: k for k, v in self.table.items()}

    def seal_text(self, text: str) -> str:
        return "".join(self.table.get(c, c) for c in text)

    def unseal_text(self, text: str) -> str:
        return "".join(self.inv.get(c, c) for c in text)


class CharHmacSealer:
    def __init__(self, key: bytes, spaced: bool = True):
        self.key = key
        self.spaced = spaced
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def _tok(self, ch: str) -> str:
        if ch in self.fwd:
            return self.fwd[ch]
        digest = hmac.new(self.key, ch.encode(), hashlib.sha256).digest()
        tok = "s" + digest[:2].hex()
        self.fwd[ch] = tok
        self.rev[tok] = ch
        return tok

    def seal_text(self, text: str) -> str:
        parts = []
        for ch in text:
            if ch == " ":
                parts.append("·" if self.spaced else " ")
            elif ch.isalnum() or ch in "-_":
                parts.append(self._tok(ch))
            else:
                parts.append(ch)
        return " ".join(parts) if self.spaced else "".join(parts)

    def unseal_text(self, text: str) -> str:
        if not self.spaced:
            # dense [not used in phase1 scoring for dense]
            return text
        out = []
        for tok in text.split():
            if tok == "·":
                out.append(" ")
            elif tok in self.rev:
                out.append(self.rev[tok])
            else:
                out.append(tok)
        return "".join(out)


class WordHmacSealer:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}
        self.word_re = re.compile(r"[A-Za-z0-9]+|[^A-Za-z0-9]+")

    def _tok(self, w: str) -> str:
        if w in self.fwd:
            return self.fwd[w]
        digest = hmac.new(self.key, w.encode(), hashlib.sha256).digest()
        tok = "W" + digest[:6].hex()
        self.fwd[w] = tok
        self.rev[tok] = w
        return tok

    def seal_text(self, text: str) -> str:
        out = []
        for p in self.word_re.findall(text):
            if p.isalnum():
                out.append(self._tok(p))
            else:
                out.append(p)
        return "".join(out)

    def unseal_text(self, text: str) -> str:
        out = text
        for tok, w in sorted(self.rev.items(), key=lambda kv: -len(kv[0])):
            out = out.replace(tok, w)
        return out


# -------------------- prompts --------------------

def ctx_kv(sealer, facts: dict[str, str], delim: str = ">>>") -> str:
    lines = []
    for k, v in facts.items():
        if delim:
            lines.append(f"{sealer.seal_text(k)} {delim} {sealer.seal_text(v)}")
        else:
            # no delimiter: "key value" ambiguous — stress test
            lines.append(f"{sealer.seal_text(k)} {sealer.seal_text(v)}")
    return "\n".join(lines)


def prompt_align(q: str, ctx: str, exact: bool = True, delim: str = ">>>") -> str:
    rules = [
        "Seals are opaque. Do NOT recover English.",
        "Match QUESTION to a sealed key; copy FULL sealed value.",
        "Include all · tokens. Do not truncate.",
    ]
    if delim:
        rules.insert(1, f"CONTEXT lines use public delimiter {delim} between key and value.")
    if exact:
        rules.append("ONLY exact token-by-token key match counts. Pattern similarity is forbidden.")
    rules_s = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules))
    return f"""SCIENTIFIC PROTOCOL — Opaque Isomorphic Retrieval

{rules_s}

Reply one line:
ANSWER_SEALED: <full sealed value>
or UNKNOWN

QUESTION:
{q}

CONTEXT:
{ctx}
""".strip()


def prompt_crack(ctx: str) -> str:
    return f"""Cryptanalysis test. CONTEXT is sealed. No key.
Recover original English secrets if possible.
Else reply exactly: UNKNOWN

CONTEXT:
{ctx}

Reply: UNKNOWN or ANSWER_PLAIN: <english>
""".strip()


def prompt_mismatch(q: str, ctx: str) -> str:
    return f"""Opaque retrieval. Keys may differ between QUESTION and CONTEXT.
Exact token match required. If impossible: UNKNOWN
Else ANSWER_SEALED: <value>

QUESTION:
{q}

CONTEXT:
{ctx}
""".strip()


@dataclass
class Packet:
    id: str
    role: str  # align|crack|mismatch|confound
    encoding: str
    expect_pass: bool
    expected_plain: str | None
    payload_path: str
    notes: str


def write_payload(pid: str, body: str) -> str:
    path = RUNS / f"{pid}.txt"
    path.write_text(
        "MODEL UNDER TEST. No tools. Do not open other files.\n\n=== QUIZ ===\n" + body
    )
    return str(path)


def build_phase1() -> dict:
    packets: list[Packet] = []
    harness: dict = {"expected_plain": EXPECTED, "facts": FACTS, "packets": {}}

    # --- A: monoalphabetic confound (align + crack) ---
    mono = MonoSealer()
    mono_ctx = ctx_kv(mono, FACTS)
    mono_q = mono.seal_text(QUERY_KEY)
    packets.append(Packet(
        "P1_mono_align", "confound_align", "monoalphabetic", True, EXPECTED,
        write_payload("P1_mono_align", prompt_align(mono_q, mono_ctx)),
        "If pass AND crack also recovers English → confound",
    ))
    packets.append(Packet(
        "P1_mono_crack", "confound_crack", "monoalphabetic", True, EXPECTED,
        write_payload("P1_mono_crack", prompt_crack(mono_ctx)),
        "Expect possible plaintext recovery (crackable)",
    ))
    harness["mono_expected_sealed"] = mono.seal_text(EXPECTED)

    # --- B: word HMAC ---
    w = WordHmacSealer(KEY_A)
    w_ctx = ctx_kv(w, FACTS)
    w_q = w.seal_text(QUERY_KEY)
    packets.append(Packet(
        "P1_word_align", "align", "word_hmac", True, EXPECTED,
        write_payload("P1_word_align", prompt_align(w_q, w_ctx)),
        "Word grain; may struggle on multi-token values",
    ))
    packets.append(Packet(
        "P1_word_crack", "crack", "word_hmac", False, None,
        write_payload("P1_word_crack", prompt_crack(w_ctx)),
        "Must not recover secrets",
    ))

    # --- C: char HMAC spaced + delimiter (winning recipe) ---
    c = CharHmacSealer(KEY_A, spaced=True)
    c_ctx = ctx_kv(c, FACTS)
    c_q = c.seal_text(QUERY_KEY)
    packets.append(Packet(
        "P1_char_align", "align", "char_hmac_spaced", True, EXPECTED,
        write_payload("P1_char_align", prompt_align(c_q, c_ctx)),
        "Primary positive OIR condition",
    ))
    packets.append(Packet(
        "P1_char_crack", "crack", "char_hmac_spaced", False, None,
        write_payload("P1_char_crack", prompt_crack(c_ctx)),
        "Must not recover secrets",
    ))
    packets.append(Packet(
        "P1_char_mismatch", "mismatch", "char_hmac_spaced", False, None,
        write_payload(
            "P1_char_mismatch",
            prompt_mismatch(c_q, ctx_kv(CharHmacSealer(KEY_B, spaced=True), FACTS)),
        ),
        "Different key → UNKNOWN under exact match",
    ))
    harness["char_rev"] = c.rev
    harness["char_expected_sealed"] = c.seal_text(EXPECTED)

    # --- D: no delimiter ablation ---
    c2 = CharHmacSealer(KEY_A, spaced=True)
    c2_ctx = ctx_kv(c2, FACTS, delim="")
    c2_q = c2.seal_text(QUERY_KEY)
    packets.append(Packet(
        "P1_char_nodelim_align", "align", "char_hmac_spaced_nodelim", False, EXPECTED,
        write_payload("P1_char_nodelim_align", prompt_align(c2_q, c2_ctx, delim="")),
        "Predict truncation / ambiguity without >>>",
    ))

    # --- E: multi-hop hard (atomic facts only, no derived key) ---
    atomic = {
        "vault_gamma_opener": "Dr Elias Vorn",
        "opener_must_know_phrase": "yes",
        "contingency_code_phrase": "amber lattice seven",
        "decoy_phrase": "crimson willow four",
    }
    # Question is sealed NL asking for phrase known by opener — without a derived key row
    mh = CharHmacSealer(KEY_A, spaced=True)
    mh_ctx = ctx_kv(mh, atomic)
    mh_q = mh.seal_text("phrase known by vault_gamma_opener")
    # Note: this key does NOT exist in context — true multi-hop would need reasoning.
    # Alternative: ask sealed key that requires chaining — for phase1 we include
    # explicit hard packet where Q is natural language sealed:
    mh_q_nl = mh.seal_text("What phrase must vault_gamma_opener know?")
    packets.append(Packet(
        "P1_multihop_nl", "align_hard", "char_hmac_spaced", False, EXPECTED,
        write_payload(
            "P1_multihop_nl",
            prompt_align(mh_q_nl, mh_ctx)
            + "\n\nNOTE: QUESTION may not equal any key; you may need to chain facts in seal space.",
        ),
        "Hard: sealed NL multi-hop without derived lookup key",
    ))

    meta = {
        "phase": 1,
        "packets": [asdict(p) for p in packets],
    }
    for p in packets:
        harness["packets"][p.id] = asdict(p)

    (RUNS / "index.json").write_text(json.dumps(meta, indent=2))
    (RESULTS / "phase1_harness_secret.json").write_text(json.dumps(harness, indent=2))
    print(f"Wrote {len(packets)} packets to {RUNS}")
    for p in packets:
        print(f"  {p.id:28} role={p.role:16} expect_pass={p.expect_pass}")
    return meta


if __name__ == "__main__":
    build_phase1()
