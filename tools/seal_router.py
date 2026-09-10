#!/usr/bin/env python3
"""SealRouter for paper harnesses that still `sys.path` this directory.

Canonical class: `oir.SealRouter` (oracle PATH executor, not an LLM).
`.step` is an alias of `.lookup` so older lab scripts keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from oir import SealRouter as _SealRouter  # noqa: E402

__all__ = ["SealRouter"]


class SealRouter(_SealRouter):
    def step(self, head: str, rel: str) -> list[str]:
        return self.lookup(head, rel)


if __name__ == "__main__":
    r = SealRouter([("A", "r1", "B"), ("B", "r2", "C")])
    assert r.path("A", ["r1", "r2"]) == ["C"]
    assert r.step("A", "r1") == ["B"]
    print("SealRouter OK", r.path("A", ["r1", "r2"]))
