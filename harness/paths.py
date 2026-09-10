"""Repo-relative paths in harness JSON so the lock is portable on GitHub."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def repo_rel(p: Path | str) -> str:
    path = Path(p)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        text = path.as_posix()
        marker = "/oir/"
        if marker in text:
            return text.split(marker, 1)[1]
        return text


def repo_abs(p: str | Path) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()
