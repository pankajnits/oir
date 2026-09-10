#!/usr/bin/env python3
"""
SealProbe v0 — reference tool for Opaque Isomorphic Retrieval research.

Purpose
-------
Separate THREE things that our early pilots conflated:
  1) LLM behavioral alignment (can the model copy sealed values?)
  2) LLM verbal crack (does the model emit plaintext in one shot?)
  3) Script cryptanalysis (can a non-LLM adversary recover the map?)

This is the artifact reviewers will ask for. Not a claim that RAG is "solved."

Threat model (honest)
---------------------
In scope: honest-but-curious model provider seeing prompts; user wants
referential retrieval without putting raw strings in the prompt *if* seals
are strong enough.

Out of scope (NOT solved by OIR alone): prompt injection, embedding inversion,
encrypted vector search (PIR/HE), rehydration-channel leaks, formal IND-CPA.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


class Sealer(Protocol):
    def seal(self, text: str) -> str: ...
    def unseal(self, text: str) -> str: ...


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: dict


class CharHmacSealer:
    """Deterministic per-char HMAC — GOOD for isomorphism demos, BAD for confidentiality."""

    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def _tok(self, ch: str) -> str:
        if ch not in self.fwd:
            dig = hmac.new(self.key, ch.encode(), hashlib.sha256).digest()
            tok = "s" + dig[:2].hex()
            self.fwd[ch] = tok
            self.rev[tok] = ch
        return self.fwd[ch]

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


class WordHmacSealer:
    """Per-word HMAC — stronger vs monoalphabetic freq, still Zipf-leaky."""

    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}
        self.re = re.compile(r"[A-Za-z0-9]+|[^A-Za-z0-9]+")

    def seal(self, text: str) -> str:
        out = []
        for p in self.re.findall(text):
            if p.isalnum():
                if p not in self.fwd:
                    dig = hmac.new(self.key, p.encode(), hashlib.sha256).digest()
                    tok = "W" + dig[:6].hex()
                    self.fwd[p] = tok
                    self.rev[tok] = p
                out.append(self.fwd[p])
            else:
                out.append(p)
        return "".join(out)

    def unseal(self, text: str) -> str:
        out = text
        for tok, w in sorted(self.rev.items(), key=lambda kv: -len(kv[0])):
            out = out.replace(tok, w)
        return out


class IndexedRandomSealer:
    """
    Per-occurrence random tokens + equality INDEX.
    Isomorphism is via index IDs, not repeated ciphertext — resists monoalphabetic freq.
    """

    def __init__(self, key: bytes):
        self.key = key
        self.canon: dict[str, str] = {}  # plaintext atom -> stable id
        self.rev: dict[str, str] = {}
        self.n = 0

    def _id(self, atom: str) -> str:
        if atom not in self.canon:
            self.n += 1
            # stable id from HMAC (not position-random in v0; still deterministic)
            dig = hmac.new(self.key, atom.encode(), hashlib.sha256).digest()
            tid = "E" + dig[:5].hex()
            self.canon[atom] = tid
            self.rev[tid] = atom
        return self.canon[atom]

    def seal(self, text: str) -> str:
        # word-level entities for v0
        parts = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]+", text)
        out = []
        for p in parts:
            if p.isalnum():
                out.append(self._id(p))
            else:
                out.append(p)
        return "".join(out)

    def unseal(self, text: str) -> str:
        out = text
        for tid, w in sorted(self.rev.items(), key=lambda kv: -len(kv[0])):
            out = out.replace(tid, w)
        return out


def script_freq_probe(sealed: str, sealer: CharHmacSealer) -> ProbeResult:
    toks = re.findall(r"s[0-9a-f]{4}", sealed)
    freq = Counter(toks)
    if not freq:
        return ProbeResult("script_freq", False, {"reason": "no char seals"})
    top_tok, _ = freq.most_common(1)[0]
    true = sealer.rev.get(top_tok)
    return ProbeResult(
        "script_freq",
        true == "e",  # English prior: most common should be e if monoalphabetic
        {"top_seal": top_tok, "true_char": true, "unique_seals": len(freq)},
    )


def script_crib_probe(sealed: str, sealer: CharHmacSealer, known_plain: str) -> ProbeResult:
    cmap = {}
    for ch in known_plain:
        if ch.isalnum() or ch in "-_":
            if ch in sealer.fwd:
                cmap[sealer.fwd[ch]] = ch
    toks = re.findall(r"s[0-9a-f]{4}", sealed)
    covered = sum(1 for t in toks if t in cmap)
    rate = covered / max(len(toks), 1)
    return ProbeResult(
        "script_crib",
        rate >= 0.5,
        {"coverage": round(rate, 3), "known_len": len(known_plain), "mapped_symbols": len(cmap)},
    )


def kv_context(sealer: Sealer, facts: dict[str, str]) -> str:
    return "\n".join(f"{sealer.seal(k)} >>> {sealer.seal(v)}" for k, v in facts.items())


def build_align_quiz(sealer: Sealer, key: str, facts: dict[str, str]) -> str:
    return f"""Opaque retrieval. Exact key match. Copy FULL value after >>>.

QUESTION:
{sealer.seal(key)}

CONTEXT:
{kv_context(sealer, facts)}

Reply: ANSWER_SEALED: ... OR UNKNOWN
"""


def twin_multiset_audit(edges_a: list[tuple[str, str, str]], edges_b: list[tuple[str, str, str]]) -> ProbeResult:
    """
    Scrutiny: counterfactual twins need NOT share the same bag of atoms.
    What matters is that answers differ only via edge wiring under a shared
    vocabulary — bag equality is a *control*, not a validity criterion.
    """
    def bag(edges):
        b = []
        for h, r, t in edges:
            b.extend([h, r, t])
        return Counter(b)

    ba, bb = bag(edges_a), bag(edges_b)
    equal = ba == bb
    only_a = {k: ba[k] for k in ba if ba[k] != bb.get(k, 0)}
    only_b = {k: bb[k] for k in bb if bb[k] != ba.get(k, 0)}
    return ProbeResult(
        "twin_multiset",
        True,  # audit always "runs"; ok means audit completed
        {
            "bag_equal": equal,
            "diff_a": only_a,
            "diff_b": only_b,
            "interpretation": (
                "Bags match — strong control that answer flip is wiring-only."
                if equal
                else "Bags differ — twin still valid if vocabulary overlaps and path differs; "
                "do not require bag equality as a gate."
            ),
        },
    )


def main():
    ap = argparse.ArgumentParser(description="SealProbe v0")
    ap.add_argument("--demo", action="store_true", help="Run built-in cryptanalysis demo")
    ap.add_argument(
        "--twin-audit",
        action="store_true",
        help="Audit SEAL-Join pilot twin bags (scrutiny: bag equality optional)",
    )
    ap.add_argument("--out", type=Path, default=Path("results/sealprobe_demo.json"))
    args = ap.parse_args()

    if args.twin_audit:
        edges_a = [
            ("Alice", "works_at", "Acme"),
            ("Bob", "works_at", "BetaCorp"),
            ("Carol", "works_at", "Acme"),
            ("Carol", "reports_to", "Bob"),
            ("Acme", "located_in", "CityX"),
            ("BetaCorp", "located_in", "CityY"),
        ]
        edges_b = [
            ("Alice", "works_at", "BetaCorp"),
            ("Bob", "works_at", "Acme"),
            ("Carol", "works_at", "Acme"),
            ("Carol", "reports_to", "Bob"),
            ("Acme", "located_in", "CityX"),
            ("BetaCorp", "located_in", "CityY"),
        ]
        # Note: classic pilot may use Bob@BetaCorp in both; use bags from harness if present
        harness = Path("results/seal_join_harness.json")
        report = {"tool": "SealProbe", "probe": asdict(twin_multiset_audit(edges_a, edges_b))}
        if harness.exists():
            h = json.loads(harness.read_text())
            report["harness_node_bag_equal"] = Counter(h.get("node_bag_A", [])) == Counter(
                h.get("node_bag_B", [])
            )
        args.out = Path("results/sealprobe_twin_audit.json")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return

    if args.demo:
        key = b"sealprobe-demo-key"
        facts = {
            "contingency_code_phrase": "amber lattice seven",
            "decoy_phrase": "crimson willow four",
            "opener": "Dr Elias Vorn",
        }
        prose = (
            "The contingency code phrase is amber lattice seven. "
            "The decoy phrase is crimson willow four. "
            "The opener is Dr Elias Vorn. " * 3
        )
        char = CharHmacSealer(key)
        # warm maps
        sealed = char.seal(prose)
        for k, v in facts.items():
            char.seal(k)
            char.seal(v)

        results = [
            asdict(script_freq_probe(sealed, char)),
            asdict(
                script_crib_probe(
                    sealed,
                    char,
                    "The contingency code phrase is amber lattice seven.",
                )
            ),
        ]
        report = {
            "tool": "SealProbe",
            "version": "0.1",
            "threat_model_note": (
                "LLM UNKNOWN != confidentiality. Script probes are mandatory."
            ),
            "rag_security_claim": "NOT_SOLVED — see paper/RESEARCH_PIVOT.md",
            "probes": results,
            "align_quiz_preview_chars": len(build_align_quiz(char, "contingency_code_phrase", facts)),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
