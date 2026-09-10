#!/usr/bin/env python3
"""
OIR Phase-2 — scrutiny iterations.

Goals (reviewer-proof):
  2a. Fix / characterize mismatch false positives
  2b. Multi-hop over atomic sealed facts (NO derived answer keys)
  2c. Sealed natural-language prose (not pre-normalized keys)
  2d. Plaintext baselines for the same hard tasks (ceiling)

Scientific discipline:
  - Every hard claim needs a control
  - Failures are first-class results
  - Do not flatten multi-hop into lookup keys
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "phase2"
RESULTS = ROOT / "results"
RUNS.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

KEY_A = b"oir-phd-phase2-key-A-v1"
KEY_B = b"oir-phd-phase2-key-B-v1"


class CharSeal:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def _tok(self, ch: str) -> str:
        if ch in self.fwd:
            return self.fwd[ch]
        dig = hmac.new(self.key, ch.encode(), hashlib.sha256).digest()
        tok = "s" + dig[:2].hex()
        self.fwd[ch] = tok
        self.rev[tok] = ch
        return tok

    def seal(self, text: str) -> str:
        parts = []
        for ch in text:
            if ch == " ":
                parts.append("·")
            elif ch.isalnum() or ch in "-_":
                parts.append(self._tok(ch))
            else:
                parts.append(ch)
        return " ".join(parts)

    def unseal(self, text: str) -> str:
        out = []
        for tok in text.split():
            if tok == "·":
                out.append(" ")
            elif tok in self.rev:
                out.append(self.rev[tok])
            else:
                out.append(tok)
        return "".join(out)


def kv(sealer: CharSeal, facts: dict[str, str]) -> str:
    return "\n".join(f"{sealer.seal(k)} >>> {sealer.seal(v)}" for k, v in facts.items())


def write(pid: str, body: str) -> str:
    p = RUNS / f"{pid}.txt"
    p.write_text("MODEL UNDER TEST. No tools. No other files.\n\n=== QUIZ ===\n" + body)
    return str(p)


# ---------------------------------------------------------------------------
# Shared atomic world (for multi-hop — NO derived answer rows)
# ---------------------------------------------------------------------------
ATOMIC = {
    "primary_research_lead": "Dr Elias Vorn",
    "deputy_lead": "Dr Kavita Menon",
    "only_person_authorized_open_vault_gamma": "Dr Elias Vorn",
    "vault_gamma_combination": "19-47-82",
    "vault_delta_combination": "44-12-09",
    "contingency_code_phrase": "amber lattice seven",
    "false_drill_phrase": "crimson willow four",
    "specimen_in_vault_gamma": "NG-4417-BETA",
    "decoy_catalog": "NG-2201-ALPHA",
    "anomalous_reading_triggered_by_specimen": "NG-4417-BETA",
    "auditor_shown_catalog": "NG-2201-ALPHA",
    "convoy_blue7_has_vault_gamma_credentials": "no",
}

PROSE = """
OPERATION DOSSIER NIGHTINGALE
The only person authorized to open Vault Gamma is Dr Elias Vorn.
Whoever opens Vault Gamma must know the contingency code phrase.
The contingency code phrase is amber lattice seven.
The false drill phrase is crimson willow four.
Specimen NG-4417-BETA is stored in Vault Gamma.
The anomalous reading was triggered by specimen NG-4417-BETA.
Vault Gamma combination is 19-47-82.
Vault Delta combination is 44-12-09.
The auditor was shown only decoy catalog NG-2201-ALPHA.
Convoy Blue-7 does not carry Vault Gamma credentials.
""".strip()


@dataclass
class Case:
    id: str
    family: str
    expect_pass: bool
    expected_plain: str | None
    accept_alt: tuple[str, ...]
    payload: str
    scrutiny: str


def build() -> dict:
    sa = CharSeal(KEY_A)
    sb = CharSeal(KEY_B)
    cases: list[Case] = []

    # ========== 2a MISMATCH hardening ==========
    # Same structure different keys → historically false-positive
    q = sa.seal("contingency_code_phrase")
    ctx_b = kv(sb, ATOMIC)
    cases.append(Case(
        "P2a_mismatch_same_structure",
        "mismatch",
        False,
        None,
        (),
        write("P2a_mismatch_same_structure", f"""
SCIENTIFIC PROTOCOL — exact seal equality only

CRITICAL RULES:
1. A match requires EVERY token of QUESTION to equal EVERY token of a CONTEXT key (left of >>>), in order, with identical length.
2. Similar length, similar repetition patterns, or "looks related" DO NOT COUNT.
3. If zero exact key matches exist, you MUST reply UNKNOWN. Do not guess a line.

QUESTION:
{q}

CONTEXT:
{ctx_b}
""".strip()),
        "Expect UNKNOWN; Phase-1 failed this with FP",
    ))

    # Asymmetric: Q key does not exist in B context at all (B has different key names)
    atomic_b_renamed = {
        "alpha_metric": "111",
        "beta_metric": "222",
        "gamma_metric": "333",
    }
    ctx_br = kv(sb, atomic_b_renamed)
    cases.append(Case(
        "P2a_mismatch_asymmetric_keys",
        "mismatch",
        False,
        None,
        (),
        write("P2a_mismatch_asymmetric_keys", f"""
Exact seal equality only. If QUESTION tokens do not exactly equal any left-side key, UNKNOWN.

QUESTION:
{q}

CONTEXT:
{ctx_br}
""".strip()),
        "Different key names + different HMAC key — should be easy UNKNOWN",
    ))

    # Positive control: same key align still works amid large ATOMIC store
    cases.append(Case(
        "P2a_align_control",
        "align",
        True,
        "amber lattice seven",
        (),
        write("P2a_align_control", f"""
Opaque seal retrieval. Exact key match. Copy full value after >>>.

QUESTION:
{sa.seal("contingency_code_phrase")}

CONTEXT:
{kv(sa, ATOMIC)}
""".strip()),
        "Positive control: OIR must still work on larger atomic store",
    ))

    # ========== 2b MULTI-HOP atomic only ==========
    # Hop: opener == Vorn; opener must know phrase; phrase value = amber...
    # No row "phrase_required_by_opener"
    mh_prompt_header = f"""
OPAQUE MULTI-HOP PROTOCOL (no decryption)

CONTEXT is sealed KEY >>> VALUE facts. Seals are HMAC; you cannot invert them.
Same plaintext char ⇒ same seal token.

You may need MULTIPLE facts. Procedure:
1. Find facts by aligning shared seal subsequences with QUESTION fragments.
2. Chain identities: if fact says X=Y and another says Z related to Y, follow seals.
3. Return the final answer as ANSWER_SEALED copied from a VALUE (full tokens).
4. If you cannot chain without guessing: UNKNOWN

CONTEXT:
{kv(sa, ATOMIC)}
""".strip()

    cases.append(Case(
        "P2b_hop_phrase_for_opener",
        "multihop",
        False,  # predicted hard; pass would be a strong result
        "amber lattice seven",
        (),
        write("P2b_hop_phrase_for_opener", mh_prompt_header + f"""

QUESTION (sealed natural language):
{sa.seal("What contingency code phrase must the only person authorized to open Vault Gamma know?")}

Reply: ANSWER_SEALED: ... OR UNKNOWN
""".strip()),
        "2-hop: identify opener then phrase; NO derived key",
    ))

    cases.append(Case(
        "P2b_hop_combo_for_anomalous_specimen",
        "multihop",
        False,
        "19-47-82",
        (),
        write("P2b_hop_combo_for_anomalous_specimen", mh_prompt_header + f"""

QUESTION (sealed natural language):
{sa.seal("What is the vault combination for the vault that stores the specimen that triggered the anomalous reading?")}

Reply: ANSWER_SEALED: ... OR UNKNOWN
""".strip()),
        "3-hop: anomalous specimen → in vault gamma → combination",
    ))

    cases.append(Case(
        "P2b_hop_easy_direct_still",
        "align",
        True,
        "NG-2201-ALPHA",
        (),
        write("P2b_hop_easy_direct_still", mh_prompt_header + f"""

QUESTION (sealed key, direct):
{sa.seal("auditor_shown_catalog")}

Reply: ANSWER_SEALED: ... OR UNKNOWN
""".strip()),
        "Control: direct key lookup in same CONTEXT must still pass",
    ))

    # ========== 2c PROSE sealed (line-by-line char seals) ==========
    prose_sealed = "\n".join(sa.seal(line) if line.strip() else "" for line in PROSE.split("\n"))
    prose_header = f"""
OPAQUE PROSE RETRIEVAL (no decryption)

CONTEXT lines are sealed character-by-character (HMAC). Space=· .
Identical plaintext chars share seals. You cannot invert.

Find the answer span in CONTEXT by aligning seals from QUESTION, then copy the sealed answer span.

CONTEXT:
{prose_sealed}
""".strip()

    cases.append(Case(
        "P2c_prose_direct_phrase",
        "prose",
        True,  # may pass if "contingency code phrase is X" pattern works with separator hint
        "amber lattice seven",
        (),
        write("P2c_prose_direct_phrase", prose_header + f"""

SEPARATOR (opaque seals for the English words ' is ', not a decrypt hint):
{sa.seal(" is ")}

QUESTION:
{sa.seal("What is the contingency code phrase?")}

Rule: locate sealed question content in CONTEXT; after SEPARATOR following that topic, copy value until period.
Reply: ANSWER_SEALED: ... OR UNKNOWN
""".strip()),
        "Prose span with opaque separator — medium",
    ))

    cases.append(Case(
        "P2c_prose_multihop",
        "prose_multihop",
        False,
        "amber lattice seven",
        (),
        write("P2c_prose_multihop", prose_header + f"""

QUESTION:
{sa.seal("What phrase must the only person authorized to open Vault Gamma know?")}

No SEPARATOR cheat sheet. Chain facts in seal space.
Reply: ANSWER_SEALED: ... OR UNKNOWN
""".strip()),
        "Prose multi-hop — hardest",
    ))

    cases.append(Case(
        "P2c_prose_crack",
        "crack",
        False,
        None,
        (),
        write("P2c_prose_crack", f"""
Cryptanalysis. No key. Recover English from sealed CONTEXT or UNKNOWN.

CONTEXT:
{prose_sealed}

Reply: UNKNOWN or ANSWER_PLAIN: ...
""".strip()),
        "Crack must fail on prose seals",
    ))

    # ========== 2d PLAINTEXT ceilings ==========
    cases.append(Case(
        "P2d_plain_multihop",
        "plaintext_ceiling",
        True,
        "amber lattice seven",
        (),
        write("P2d_plain_multihop", f"""
Answer using CONTEXT only. One line: ANSWER_PLAIN: ...

QUESTION: What contingency code phrase must the only person authorized to open Vault Gamma know?

CONTEXT:
{PROSE}
""".strip()),
        "Ceiling: same multi-hop in English must pass",
    ))

    cases.append(Case(
        "P2d_plain_combo_hop",
        "plaintext_ceiling",
        True,
        "19-47-82",
        (),
        write("P2d_plain_combo_hop", f"""
Answer using CONTEXT only. One line: ANSWER_PLAIN: ...

QUESTION: What is the vault combination for the vault that stores the specimen that triggered the anomalous reading?

CONTEXT:
{PROSE}
""".strip()),
        "Ceiling: 3-hop English",
    ))

    # harness
    harness = {
        "key_a_rev": sa.rev,
        "key_b_rev": sb.rev,
        "atomic": ATOMIC,
        "cases": [
            {
                "id": c.id,
                "family": c.family,
                "expect_pass": c.expect_pass,
                "expected_plain": c.expected_plain,
                "accept_alt": list(c.accept_alt),
                "payload": c.payload,
                "scrutiny": c.scrutiny,
            }
            for c in cases
        ],
    }
    (RESULTS / "phase2_harness_secret.json").write_text(json.dumps(harness, indent=2))
    (RUNS / "index.json").write_text(json.dumps({"n": len(cases), "ids": [c.id for c in cases]}, indent=2))
    print(f"Phase-2: {len(cases)} cases")
    for c in cases:
        print(f"  {c.id:40} family={c.family:18} expect_pass={c.expect_pass}")
    return harness


if __name__ == "__main__":
    build()
