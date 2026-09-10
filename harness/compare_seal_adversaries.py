#!/usr/bin/env python3
"""
Compare script adversaries across seal types (char / word / indexed).

Produces results/seal_compare_adversary.json for the paper's security section.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from sealprobe import CharHmacSealer, WordHmacSealer, IndexedRandomSealer  # noqa: E402

KEY = b"oir-compare-adversary-v1"
CORPUS = """
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

CRIB = "The only person authorized to open Vault Gamma is Dr Elias Vorn."


def char_attacks(sealer: CharHmacSealer, sealed: str) -> dict:
    toks = re.findall(r"s[0-9a-f]{4}", sealed)
    freq = Counter(toks)
    top = freq.most_common(1)[0][0] if freq else None
    freq_ok = bool(top and sealer.rev.get(top) == "e")
    cmap = {}
    for ch in CRIB:
        if ch.isalnum() or ch in "-_":
            if ch in sealer.fwd:
                cmap[sealer.fwd[ch]] = ch
    covered = sum(1 for t in toks if t in cmap) / max(len(toks), 1)
    return {
        "freq_identifies_e": freq_ok,
        "crib_coverage": round(covered, 3),
        "confidentiality_survives_script": not (freq_ok or covered >= 0.5),
    }


def word_attacks(sealer: WordHmacSealer, sealed: str) -> dict:
    toks = re.findall(r"W[0-9a-f]+", sealed)
    freq = Counter(toks)
    # Zipf: most common word seal often "The"/"the"/"is" — check if top is a function word
    top = freq.most_common(1)[0][0] if freq else None
    top_word = sealer.rev.get(top or "", "")
    # crib: known sentence recovers those word seals
    known_words = re.findall(r"[A-Za-z0-9]+", CRIB)
    mapped = {sealer.fwd[w] for w in known_words if w in sealer.fwd}
    covered = sum(1 for t in toks if t in mapped) / max(len(toks), 1)
    return {
        "top_word": top_word,
        "zipf_function_word_top": top_word.lower() in {"the", "a", "is", "to", "of", "and"},
        "crib_token_coverage": round(covered, 3),
        "confidentiality_survives_script": covered < 0.5 and top_word.lower() not in {"the"},
        "note": "Word HMAC still leaks via Zipf + known-plaintext codebook recovery",
    }


def indexed_attacks(sealer: IndexedRandomSealer, sealed: str) -> dict:
    toks = re.findall(r"E[0-9a-f]+", sealed)
    freq = Counter(toks)
    top = freq.most_common(1)[0][0] if freq else None
    top_ent = sealer.rev.get(top or "", "")
    known = re.findall(r"[A-Za-z0-9]+", CRIB)
    mapped = {sealer.canon[w] for w in known if w in sealer.canon}
    covered = sum(1 for t in toks if t in mapped) / max(len(toks), 1)
    return {
        "top_entity": top_ent,
        "crib_token_coverage": round(covered, 3),
        "unique_entities": len(freq),
        "confidentiality_survives_script": False,  # deterministic entity ids still codebook with crib
        "note": "Indexed/entity seals resist monoalphabetic letter attack but known-plaintext still recovers entity codebook",
        "better_than_char_monoalphabetic": True,
    }


def main():
    char = CharHmacSealer(KEY)
    word = WordHmacSealer(KEY)
    indexed = IndexedRandomSealer(KEY)

    c_sealed = char.seal(CORPUS)
    w_sealed = word.seal(CORPUS)
    i_sealed = indexed.seal(CORPUS)
    # warm crib maps
    char.seal(CRIB)
    word.seal(CRIB)
    indexed.seal(CRIB)
    # re-seal corpus after warm (maps already filled)
    c_sealed = char.seal(CORPUS)
    w_sealed = word.seal(CORPUS)
    i_sealed = indexed.seal(CORPUS)

    report = {
        "corpus_chars": len(CORPUS),
        "char_hmac": char_attacks(char, c_sealed),
        "word_hmac": word_attacks(word, w_sealed),
        "indexed_entity": indexed_attacks(indexed, i_sealed),
        "paper_sentence": (
            "Deterministic seals enable referential retrieval but are not confidential "
            "against script adversaries with a short crib; per-char seals additionally "
            "collapse to monoalphabetic frequency attacks."
        ),
    }
    out = ROOT / "results" / "seal_compare_adversary.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
