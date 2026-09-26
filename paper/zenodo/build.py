#!/usr/bin/env python3
"""Named TMLR-style preprint for Zenodo. No NeurIPS checklist, no review header."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "arxiv_upload" / "main.tex"
TMLR = ROOT.parent / "tmlr"
sys.path.insert(0, str(TMLR))
from convert_from_arxiv import move_table_captions  # noqa: E402

FIGS = [
    "fig1_matched_2x2.png",
    "fig3_dualpath.png",
    "fig7_opaque_rel_n200.png",
]
STYLES = ["tmlr.sty", "fancyhdr.sty", "tmlr.bst"]

PREAMBLE = r"""\documentclass[10pt]{article} % For LaTeX2e
\usepackage[preprint]{tmlr}

\usepackage{amsmath,amssymb}
\usepackage{xcolor}
\usepackage{booktabs,array,tabularx}
\usepackage{graphicx}
\usepackage{placeins}
\usepackage{hyperref}
\usepackage{url}
\usepackage{microtype}

\hypersetup{
  pdftitle={When Can Language Models Join Without Relation Names?},
  pdfauthor={Pankaj Pandey},
  pdfsubject={Unique-Path Traversal versus End-to-End Accuracy under Path Ambiguity},
  colorlinks=false,
  pdfborder={0 0 0},
  breaklinks=true
}
\graphicspath{{./}}
\emergencystretch=2em
\setlength{\textfloatsep}{8pt plus 2pt minus 4pt}
\setlength{\floatsep}{8pt plus 2pt minus 4pt}
\setlength{\intextsep}{8pt plus 2pt minus 4pt}
\setlength{\abovedisplayskip}{6pt plus 2pt minus 3pt}
\setlength{\belowdisplayskip}{6pt plus 2pt minus 3pt}
\setlength{\abovedisplayshortskip}{4pt plus 1pt minus 2pt}
\setlength{\belowdisplayshortskip}{4pt plus 1pt minus 2pt}

\title{When Can Language Models Join\\
Without Relation Names?\\
Unique-Path Traversal versus End-to-End Accuracy\\
under Path Ambiguity%
\thanks{Large language models were used as writing assistants for grammar
and phrasing. All ideas, claims, experimental design, locked numbers, and
scientific conclusions are the authors'.}}

\author{\name Pankaj Pandey \email mightypp.nits@gmail.com \\
 \addr Independent researcher, India \\
 \url{https://github.com/pankajnits/oir}}

\begin{document}
\maketitle
"""


def extract_abstract_and_body(src: str) -> tuple[str, str]:
    m = re.search(r"\\begin\{abstract\}.*?\\end\{abstract\}", src, re.DOTALL)
    if not m:
        raise SystemExit("abstract not found")
    body = re.sub(r"\n\\clearpage\s*\\input\{checklist\}\s*", "\n", src[m.end() :])
    if r"\input{checklist}" in body or "NeurIPS Paper Checklist" in body:
        raise SystemExit("NeurIPS checklist still in the Zenodo body")
    if "github.com/pankajnits/oir" not in body:
        raise SystemExit("GitHub link missing from the appendix")
    return m.group(0), body


def link_to(name: str, target: Path) -> None:
    dest = ROOT / name
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    dest.symlink_to(target)


def main() -> None:
    abstract, body = extract_abstract_and_body(SRC.read_text())
    out = move_table_captions(PREAMBLE + "\n" + abstract + body)
    (ROOT / "main.tex").write_text(out)
    for name in STYLES:
        link_to(name, Path("..") / "tmlr" / name)
    for name in FIGS:
        link_to(name, Path("..") / "arxiv_upload" / name)
    subprocess.run(["tectonic", "-X", "compile", "main.tex"], cwd=ROOT, check=True)
    public = ROOT / "oir-preprint.pdf"
    (ROOT / "main.pdf").replace(public)
    print(f"wrote {public.relative_to(ROOT.parent.parent)}")


if __name__ == "__main__":
    main()
