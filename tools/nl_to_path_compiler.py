#!/usr/bin/env python3
"""
Deterministic NL → sealed path-program compiler.

Compiles HQ-of-employer questions against a person lexicon into:
  PATH_QUERY / START <person> / R1 works_at / R2 headquartered_in
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

PATH_HQ_OF_EMPLOYER = ("works_at", "headquartered_in")

DEFAULT_TEMPLATES = [
    "Where is the company headquartered_in that {person} works_at?",
    "In which city is the employer of {person} based?",
    "What is the HQ location of the firm where {person} works?",
    "Find the head office city for {person}'s company.",
    "Which place is {person}'s employer headquartered in?",
]

HQ_CUES = (
    "headquarter",
    "hq",
    "employer",
    "works_at",
    "works at",
    "based",
    "head office",
    "firm where",
    "company",
    "city",
    "location",
    "place",
)


@dataclass
class CompileResult:
    ok: bool
    person: str | None
    path: tuple[str, ...] | None
    program_plain: str
    reason: str

    def to_dict(self):
        return asdict(self)


class PathCompiler:
    """Lexicon + intent-cue compiler. No LLM in the loop."""

    def __init__(self, lexicon_persons: set[str], path=PATH_HQ_OF_EMPLOYER):
        self.lexicon = lexicon_persons
        self.path = path
        self._names = sorted(lexicon_persons, key=len, reverse=True)

    def compile(self, nl: str) -> CompileResult:
        text = nl.strip()
        person = None
        for name in self._names:
            variants = {name, name.replace("_", " ")}
            for v in variants:
                if v in text or v.lower() in text.lower():
                    person = name
                    break
            if person:
                break
        if not person:
            return CompileResult(False, None, None, "", "no_person_in_lexicon")

        low = text.lower()
        if not any(c in low for c in HQ_CUES):
            return CompileResult(False, person, None, "", "intent_not_hq_path")

        r1, r2 = self.path
        prog = (
            f"PATH_QUERY\n"
            f"START {person}\n"
            f"R1 {r1}\n"
            f"R2 {r2}\n"
            f"Execute START -R1-> x -R2-> y. Return y only."
        )
        return CompileResult(True, person, self.path, prog, "ok")

    def seal_program(self, person: str, seal_fn) -> str:
        """Emit path program with entity/relation atoms sealed; keep syntax words."""
        r1, r2 = self.path
        return (
            f"PATH_QUERY\n"
            f"START {seal_fn(person)}\n"
            f"R1 {seal_fn(r1)}\n"
            f"R2 {seal_fn(r2)}\n"
            f"Execute START -R1-> x -R2-> y. Return y seal only."
        )
