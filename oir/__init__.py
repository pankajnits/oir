#!/usr/bin/env python3
"""Opaque Isomorphic Reasoning — generic core.

Borrow patterns from cleartext cousins (Text-to-SQL, PyRAG, DSPy):
  load dataset → compile NL to binder program → seal → execute / MUT → score

Opacity is our layer; enrichment forms are theirs.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any


def _package_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.is_file():
        m = re.search(r'(?m)^version = "([^"]+)"', pyproject.read_text())
        if m:
            return m.group(1)
    try:
        return _pkg_version("oir-layer")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _package_version()

__all__ = [
    "EntitySeal",
    "SealRouter",
    "Program",
    "CompileResult",
    "path_program",
    "lookup_program",
    "count_program",
    "raw_nl_program",
    "execute_program",
    "MiddleLayer",
    "LayerCall",
    "SealedChat",
    "OpenAIChatClient",
    "ChatCompleter",
    "parse_sealed_answer",
    "LeakError",
    "__version__",
]


# ---------------------------------------------------------------------------
# Sealing
# ---------------------------------------------------------------------------


class EntitySeal:
    """Deterministic HMAC atom sealer. Same plaintext → same seal (isomorphism).

    ``strict=True`` (default) refuses two distinct raw spellings that would
    share a normalized form. Whitespace still folds (``Michael Eisner`` ≡
    ``Michael_Eisner``). Use ``strict=False`` only to rebuild legacy locks.
    """

    # ASCII atoms (incl. _.-) or a run of Unicode letters/digits (CJK, …).
    _PIECE = re.compile(r"[A-Za-z0-9_.\-]+|[^\W_]+|[^A-Za-z0-9_.\-]+")
    _ATOM = re.compile(r"[A-Za-z0-9_.\-]+|[^\W_]+")

    def __init__(self, key: bytes | str, prefix: str = "E", nbytes: int = 6, *, strict: bool = True):
        self.key = key.encode() if isinstance(key, str) else key
        self.prefix = prefix
        self.nbytes = nbytes
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}
        # strict: refuse to give two distinct raw spellings one seal. Raw spellings
        # are compared after folding whitespace to "_" (so "Michael Eisner" and
        # "Michael_Eisner" still bind to one atom, as documented). strict=False
        # reproduces the pre-review behaviour for rebuilding legacy locks.
        self.strict = strict
        self.raw_of: dict[str, str] = {}

    @staticmethod
    def normalize(a: str) -> str:
        a = re.sub(r"\s+", "_", str(a).strip())
        # Paper HMAC lock: ASCII atoms strip punctuation the same way as the frozen JSON.
        paper = re.sub(r"[^A-Za-z0-9_.\-]+", "_", a).strip("_")
        if paper:
            return paper[:64]
        # Pure non-Latin (e.g. CJK): keep letters/digits instead of collapsing to EMPTY.
        uni = re.sub(r"[^\w.\-]+", "_", a).strip("_")
        return (uni[:64] if uni else "EMPTY")

    @staticmethod
    def assert_raw_injective(atoms: Iterable[str]) -> None:
        """Reject an instance if two distinct raw strings share a normalized form.

        Whitespace folding matches ``atom()`` (``Michael Eisner`` ≡ ``Michael_Eisner``).
        """
        seen: dict[str, str] = {}
        for raw in atoms:
            folded = re.sub(r"\s+", "_", str(raw).strip())
            n = EntitySeal.normalize(raw)
            prev = seen.get(n)
            if prev is not None and prev != folded:
                raise ValueError(f"normalize collision: {prev!r} and {raw!r} -> {n!r}")
            seen[n] = folded

    @classmethod
    def pieces(cls, s: str) -> list[str]:
        return cls._PIECE.findall(s)

    @classmethod
    def is_atom_token(cls, p: str) -> bool:
        return bool(p and cls._ATOM.fullmatch(p))

    def is_hmac_atom(self, token: str) -> bool:
        """True iff token is prefix + nbytes×2 hex (not English that merely starts with E)."""
        nhex = self.nbytes * 2
        return bool(
            token and re.fullmatch(rf"{re.escape(self.prefix)}[0-9a-f]{{{nhex}}}", token, re.I)
        )

    def canonical_atom(self, token: str) -> str:
        """Prefix + lowercase hex, so ``EABC…`` unseals the stored ``Eabc…``."""
        t = (token or "").strip()
        if self.is_hmac_atom(t):
            return self.prefix + t[len(self.prefix) :].lower()
        return t

    def atom(self, a: str) -> str:
        raw = re.sub(r"\s+", "_", str(a).strip())
        a = self.normalize(a)
        if self.strict:
            prev_raw = self.raw_of.setdefault(a, raw)
            if prev_raw != raw:
                raise ValueError(
                    f"normalize collision: {prev_raw!r} and {raw!r} -> {a!r}; distinct names "
                    "would share one seal (use strict=False only to rebuild legacy locks)"
                )
        if a not in self.fwd:
            d = hmac.new(self.key, a.encode(), hashlib.sha256).digest()
            t = self.prefix + d[: self.nbytes].hex()
            prev = self.rev.get(t)
            if prev is not None and prev != a:
                raise ValueError(f"HMAC collision: {prev!r} vs {a!r} -> {t}")
            self.fwd[a] = t
            self.rev[t] = a
        return self.fwd[a]

    def text(self, s: str) -> str:
        return "".join(
            self.atom(p) if self.is_atom_token(p) else p for p in self.pieces(s)
        )

    def triple(self, h: str, r: str, t: str) -> tuple[str, str, str]:
        return self.atom(h), self.atom(r), self.atom(t)


# ---------------------------------------------------------------------------
# Graph + executor (SealRouter pattern — exact upper bound)
# ---------------------------------------------------------------------------

Triple = tuple[str, str, str]


class SealRouter:
    """Exact LOOKUP / path over sealed or plaintext triples."""

    def __init__(self, triples: Sequence[Triple]):
        self.triples = list(triples)
        self.index: dict[tuple[str, str], list[str]] = {}
        for h, r, t in triples:
            self.index.setdefault((h, r), []).append(t)

    def lookup(self, head: str, rel: str) -> list[str]:
        return list(self.index.get((head, rel), []))

    def path(self, start: str, rels: Sequence[str]) -> list[str]:
        frontier = [start]
        for rel in rels:
            nxt: list[str] = []
            for h in frontier:
                nxt.extend(self.lookup(h, rel))
            frontier = nxt
        return frontier

    def count_rel(self, rel: str) -> int:
        return sum(1 for _, r, _ in self.triples if r == rel)

    def render(self, sep: str = " | ") -> str:
        return "\n".join(f"{h}{sep}{r}{sep}{t}" for h, r, t in self.triples)


# ---------------------------------------------------------------------------
# Binder programs (enrichment forms under opacity)
# ---------------------------------------------------------------------------


@dataclass
class Program:
    """Executable binder — the enrichment artifact (PyRAG/SQL cousin)."""

    kind: str  # PATH | LOOKUP | COUNT | RAW_NL
    body: str
    expect: str | None = None
    meta: dict = field(default_factory=dict)

    def seal(self, sealer: EntitySeal, seal_keys: Iterable[str] | None = None) -> Program:
        """Seal atom fields listed in meta['atoms'] or seal_keys; keep syntax words."""
        atoms = list(seal_keys or self.meta.get("atoms") or [])
        body = self.body
        # longest-first replace to avoid partial collisions
        for a in sorted(atoms, key=len, reverse=True):
            body = body.replace(a, sealer.atom(a))
        expect = sealer.atom(self.expect) if self.expect else None
        return Program(self.kind, body, expect, dict(self.meta))


def path_program(start: str, rels: Sequence[str], expect: str | None = None) -> Program:
    lines = ["PATH_QUERY", f"START {start}"]
    atoms = [start, *rels]
    for i, r in enumerate(rels, 1):
        lines.append(f"R{i} {r}")
    lines.append("Execute path; return final tail only.")
    return Program("PATH", "\n".join(lines), expect, {"atoms": atoms, "start": start, "rels": list(rels)})


def lookup_program(row: str, col: str, expect: str | None = None) -> Program:
    body = (
        f"SEALED_DSL\nROW {row}\nCOL {col}\nRETURN LOOKUP(ROW, COL)\n"
        "Execute exact triple match in CONTEXT."
    )
    return Program("LOOKUP", body, expect, {"atoms": [row, col], "row": row, "col": col})


def count_program(rel: str, expect: str | int | None = None) -> Program:
    body = f"SEALED_DSL\nCOUNT triples WHERE rel = {rel}\nReturn integer count."
    exp = str(expect) if expect is not None else None
    return Program("COUNT", body, exp, {"atoms": [rel], "rel": rel})


def raw_nl_program(question: str, expect: str | None = None) -> Program:
    return Program("RAW_NL", question, expect, {"atoms": []})


def execute_program(prog: Program, router: SealRouter) -> list[str]:
    """Symbolic execution (SealRouter upper bound)."""
    if prog.kind == "PATH":
        return router.path(prog.meta["start"], prog.meta["rels"])
    if prog.kind == "LOOKUP":
        return router.lookup(prog.meta["row"], prog.meta["col"])
    if prog.kind == "COUNT":
        return [str(router.count_rel(prog.meta["rel"]))]
    raise ValueError(f"cannot symbolically execute kind={prog.kind}")


# ---------------------------------------------------------------------------
# Compiler registry (Text-to-SQL / PyRAG-style family front-ends)
# ---------------------------------------------------------------------------


@dataclass
class CompileResult:
    ok: bool
    program: Program | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.program:
            d["program"] = asdict(self.program)
        return d


class PathFamilyCompiler:
    """Deterministic NL → PATH for one relation family (like a Text-to-SQL template)."""

    def __init__(
        self,
        lexicon: set[str],
        path: Sequence[str],
        intent_cues: Sequence[str],
        expect_fn: Callable[[str], str] | None = None,
    ):
        self.lexicon = lexicon
        self.path = list(path)
        self.cues = [c.lower() for c in intent_cues]
        self.expect_fn = expect_fn
        self._names = sorted(lexicon, key=len, reverse=True)

    def compile(self, nl: str) -> CompileResult:
        person = None
        for name in self._names:
            for v in {name, name.replace("_", " ")}:
                if v in nl or v.lower() in nl.lower():
                    person = name
                    break
            if person:
                break
        if not person:
            return CompileResult(False, None, "no_lexicon_hit")
        if not any(c in nl.lower() for c in self.cues):
            return CompileResult(False, None, "intent_cue_miss")
        expect = self.expect_fn(person) if self.expect_fn else None
        return CompileResult(True, path_program(person, self.path, expect), "ok")


# ---------------------------------------------------------------------------
# MUT batch packing
# ---------------------------------------------------------------------------


def pack_mut_batch(
    items: Sequence[tuple[str, Program, str]],
    header: str,
    *,
    seal_question: bool = False,
    sealer: EntitySeal | None = None,
) -> str:
    """items: (id, program, context_text)."""
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>",
        "",
        header,
        "",
    ]
    for cid, prog, ctx in items:
        q = prog.body
        if seal_question and sealer and prog.kind == "RAW_NL":
            q = sealer.text(q)
        elif sealer and prog.kind != "RAW_NL":
            q = prog.seal(sealer).body if prog.meta.get("atoms") else q
        lines.append(f"##### ID {cid} #####\n{q}\n\nCONTEXT:\n{ctx}\n")
    return "\n".join(lines)


from .chat import ChatCompleter, OpenAIChatClient, SealedChat, parse_sealed_answer  # noqa: E402
from .errors import LeakError  # noqa: E402
from .layer import LayerCall, MiddleLayer  # noqa: E402


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
