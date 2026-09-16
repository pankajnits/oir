#!/usr/bin/env python3
"""Build the anonymous TMLR manuscript from paper/arxiv_upload/main.tex."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "arxiv_upload" / "main.tex"
FIGS = [
    "fig1_matched_2x2.png",
    "fig3_dualpath.png",
    "fig7_opaque_rel_n200.png",
]

PREAMBLE = r"""\documentclass[10pt]{article} % For LaTeX2e
\usepackage{tmlr}
% Review PDF: \usepackage{tmlr}  (this file)
% Camera-ready: \usepackage[accepted]{tmlr} and restore CAMERA_READY_AUTHOR.txt
% Named preprint: \usepackage[preprint]{tmlr}

\usepackage{amsmath,amssymb}
\usepackage{xcolor}
\usepackage{booktabs,array,tabularx}
\usepackage{graphicx}
\usepackage{placeins}
\usepackage{hyperref}
\usepackage{url}

\hypersetup{
  pdftitle={When Can Language Models Join Without Lexical Cues?},
  pdfauthor={Anonymous authors},
  pdfsubject={Unique-Path Traversal versus End-to-End Accuracy under Path Ambiguity},
  colorlinks=false,
  pdfborder={0 0 0},
  breaklinks=true
}
\graphicspath{{./}}
\emergencystretch=2em

\title{When Can Language Models Join\\
Without Lexical Cues?\\
Unique-Path Traversal versus End-to-End Accuracy\\
under Path Ambiguity%
\thanks{Large language models were used as writing assistants for grammar
and phrasing. All ideas, claims, experimental design, locked numbers, and
scientific conclusions are the authors'.}}

% Hidden while tmlr is loaded without [accepted] or [preprint].
\author{\name Anonymous authors \email anonymous@openreview \\
 \addr Anonymous affiliation}

\def\month{09}
\def\year{2026}
\def\openreview{\url{https://openreview.net/forum?id=XXXX}}

\begin{document}
\maketitle
"""

def extract_abstract_and_body(src: str) -> tuple[str, str]:
    m = re.search(r"\\begin\{abstract\}.*?\\end\{abstract\}", src, re.DOTALL)
    if not m:
        raise SystemExit("abstract not found")
    body = src[m.end() :]
    body = re.sub(r"\n\\clearpage\s*\\input\{checklist\}\s*", "\n", body)
    body = body.replace(
        r"\section*{Ethical considerations}",
        r"\subsubsection*{Broader Impact Statement}",
    )
    body = body.replace(
        r"\url{https://github.com/pankajnits/oir/releases/tag/v1.0.6}",
        "the supplementary archive",
    )
    body = body.replace(
        r"\url{https://github.com/pankajnits/oir}",
        "the supplementary archive",
    )
    leaks = [
        "pankajnits",
        "Pankaj",
        "mightypp",
        "neurips_2026",
        "fontspec",
        "TeXGyre",
    ]
    for needle in leaks:
        if needle.lower() in body.lower() and needle in (
            "pankajnits",
            "Pankaj",
            "mightypp",
        ):
            raise SystemExit(f"identity leak remaining: {needle}")
    return m.group(0), body


def move_table_captions(tex: str) -> str:
    """TMLR wants the table title before the tabular."""

    def one_table(m: re.Match[str]) -> str:
        full = m.group(0)
        head_m = re.match(r"\\begin\{table\}(?:\[[^\]]*\])?", full)
        assert head_m is not None
        head = head_m.group(0)
        inner = full[len(head) : -len(r"\end{table}")]
        cap = re.search(
            r"(\\caption\{(?:[^{}]|\{[^{}]*\})*\}\s*\\label\{[^}]+\})",
            inner,
            re.DOTALL,
        )
        tab = re.search(
            r"(\\begin\{tabularx?\}.*?\\end\{tabularx?\})", inner, re.DOTALL
        )
        if not cap or not tab:
            return full
        if cap.start() < tab.start():
            return full
        without = inner[: cap.start()] + inner[cap.end() :]
        prefix = re.match(
            r"((?:\s|\\centering|\\small|\\footnotesize|\\setlength\{[^}]+\}\{[^}]+\})*)",
            without,
        )
        assert prefix is not None
        insert_at = prefix.end()
        new_inner = (
            without[:insert_at] + "\n" + cap.group(1) + "\n" + without[insert_at:]
        )
        return head + new_inner + r"\end{table}"

    return re.sub(
        r"\\begin\{table\}(?:\[[^\]]*\])?(.*?)\\end\{table\}",
        one_table,
        tex,
        flags=re.DOTALL,
    )


def main() -> None:
    src = SRC.read_text()
    abstract, body = extract_abstract_and_body(src)
    out = PREAMBLE + "\n" + abstract + body
    out = move_table_captions(out)
    (ROOT / "main.tex").write_text(out)
    for name in FIGS:
        shutil.copy2(ROOT.parent / "arxiv_upload" / name, ROOT / name)
    print(f"wrote {(ROOT / 'main.tex').relative_to(ROOT.parent.parent)} ({len(out.splitlines())} lines)")


if __name__ == "__main__":
    main()
