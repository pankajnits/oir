#!/usr/bin/env python3
"""Build an anonymized TMLR supplementary ZIP (<= 100MB)."""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "oir-tmlr-supplementary.zip"
STAGE = Path(__file__).resolve().parent / "_supp_stage"

INCLUDE_DIRS = (
    "oir",
    "tests",
    "harness",
    "examples",
    "data",
    "tools",
    "bench",
    "results",
    "runs",
)
INCLUDE_FILES = (
    "pyproject.toml",
    "LICENSE",
    "NOTICE",
    "MANIFEST.in",
    ".gitignore",
    "SCIENTIST.md",
    "CONTRIBUTING.md",
)

SKIP_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".venv",
    "oir_layer.egg-info",
    "fonts",
    "arxiv_upload",
    "paper",
    "tmlr",
}
SKIP_SUFFIXES = {".pt", ".pyc", ".log", ".DS_Store", ".pdf"}
SKIP_NAME_FRAGMENTS = ("longctx_1m",)
SKIP_FILE_NAMES = {
    "wiki_entities_kb.txt",
    "_pdf_text.txt",
    "CAMERA_READY_AUTHOR.txt",
    "CITATION.cff",
}

REPLACEMENTS = [
    ("Pankaj Pandey", "Anonymous authors"),
    ("mightypp.nits@gmail.com", "anonymous@openreview"),
    (
        "https://github.com/pankajnits/oir/issues",
        "this archive has no public issue tracker",
    ),
    ("https://github.com/pankajnits/oir", "(this supplementary archive)"),
    ("github.com/pankajnits/oir", "(this supplementary archive)"),
    ("pankajnits", "anonymous"),
]


def skip_path(path: Path) -> bool:
    if path.name in SKIP_DIR_NAMES or path.name.endswith(".egg-info"):
        return True
    if path.name in SKIP_FILE_NAMES:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    if any(frag in path.name for frag in SKIP_NAME_FRAGMENTS):
        return True
    return False


# Collapse machine-local checkouts to repo-relative paths
# (/Users/<name>/.../oir/results/... → results/...).
_ABS_OIR = re.compile(r"/Users/[^/\"'\s]+(?:/[^/\"'\s]+)*?/oir/")


def anonymize_bytes(data: bytes, rel: str) -> bytes:
    if path_is_text(rel):
        text = data.decode("utf-8", errors="replace")
        for a, b in REPLACEMENTS:
            text = text.replace(a, b)
        text = _ABS_OIR.sub("", text)
        return text.encode("utf-8")
    return data


def path_is_text(rel: str) -> bool:
    return Path(rel).suffix.lower() in {
        "",
        ".md",
        ".txt",
        ".toml",
        ".cfg",
        ".in",
        ".py",
        ".yml",
        ".yaml",
        ".json",
        ".jsonl",
        ".csv",
        ".tex",
        ".gitignore",
        ".cff",
    } or Path(rel).name in {"LICENSE", "NOTICE", "MANIFEST.in"}


ANON_README = """# OIR — anonymous TMLR supplementary

This archive is the double-blind review copy of the code, isolation quizzes,
and locked scores. Do not search for a public repository.

Python >= 3.10.

```bash
pip install -e '.[dev]'
python3 -m pytest tests/ -q
shasum -c results/SHA256SUMS
```

`runs/` holds isolation quizzes. `results/` holds locked exact-match JSON
and per-item replies. `results/SHA256SUMS` is the hash pin cited in the paper.
Ignored megabyte packs (`longctx_1m*`) and local weight files (`*.pt`) are
not in this zip.

Primary OpenAI n=200 locks: `results/factorial_2x2_iso_n200_gpt56n200.json`
(named-arm **38/200**) and `results/header_decoy_ablation_iso_n200_gpt56n200abl.json`.
The 512-token H5-cyclic arm is `gpt56n200h512` (**134/200**; other arms in that
file are missing, not scores). Hashed-id unique-path no ARM (16 Sep, 512 tokens):
`gpt56n200uninone` (**200/200**); n=32 `gpt56uninone` (**27/32**, city **26/26**).
n=32 11 Sep: named-arm `gpt56sep` (**5/32**, other arms missing) is not the
hashed-id 512 lock `gpt56abl512` (**20/32**).
Alias k=3 does not replace those locks:
`gpt56n200k3r2` / `gpt56n200k3r3` (**46/200**, **43/200**) and
`gpt56n200h512k3r2` / `gpt56n200h512k3r3` (**130/200**, **127/200**).
n=32 August locks are unchanged. Verify with `shasum -c results/SHA256SUMS`.

Reproduce without an API: `SCIENTIST.md` and `bench/README.md`.
Composer/Grok cells used a vendor agent SDK, not the OpenAI API.

The manuscript PDF is the OpenReview submission file, not this zip.
Named preprint sources (`paper/arxiv_upload/`) and citation files are
omitted on purpose.
"""


def main() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir()
    (STAGE / "README.md").write_text(ANON_README)

    for name in INCLUDE_FILES:
        src = ROOT / name
        if not src.exists():
            continue
        dst = STAGE / name
        dst.write_bytes(anonymize_bytes(src.read_bytes(), name))

    for dirname in INCLUDE_DIRS:
        src_root = ROOT / dirname
        if not src_root.exists():
            continue
        for src in src_root.rglob("*"):
            rel = src.relative_to(ROOT)
            if any(skip_path(p) for p in [src, *src.parents]):
                continue
            if src.is_dir():
                continue
            dst = STAGE / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(anonymize_bytes(src.read_bytes(), str(rel)))

    if OUT.exists():
        OUT.unlink()
    leaks = []
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in STAGE.rglob("*"):
            if path.is_dir():
                continue
            arc = path.relative_to(STAGE).as_posix()
            zf.write(path, arcname=arc)
            if path_is_text(arc):
                text = path.read_text(errors="replace")
                for n in (
                    "Pankaj Pandey",
                    "pankajnits",
                    "mightypp",
                    "github.com/pankaj",
                    "/Users/",
                    "Pankaj",
                    "(this supplementary archive)/issues",
                ):
                    if n in text:
                        leaks.append(f"{arc}: {n}")
    shutil.rmtree(STAGE)
    size_mb = OUT.stat().st_size / (1024 * 1024)
    print(f"wrote {OUT} ({size_mb:.1f} MB)")
    if size_mb >= 100:
        raise SystemExit("zip exceeds TMLR 100MB supplementary limit")
    if leaks:
        raise SystemExit("identity leaks:\n" + "\n".join(leaks[:20]))
    print("anonymity scan: clean")


if __name__ == "__main__":
    main()
