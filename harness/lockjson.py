"""Write paper result JSON without clobbering locks or ASCII-escaping names.

Isolation scorers that emit ``results/*_{tag}.json`` must go through here.
A missing ``--force`` on an existing file is a failed score, not a rewrite.
"""
from __future__ import annotations

import json
from pathlib import Path


def write_lock(path: Path, obj: dict, *, force: bool = False) -> None:
    path = Path(path)
    if path.exists() and not force:
        raise SystemExit(f"refusing to overwrite {path}; pass --force")
    if path.exists():
        try:
            prev_note = json.loads(path.read_text()).get("note")
        except json.JSONDecodeError:
            prev_note = None
        if prev_note and "note" not in obj:
            obj["note"] = prev_note
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
