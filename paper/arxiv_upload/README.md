# arXiv source

Compiled PDF: [`main.pdf`](main.pdf) (9 content pages + references + appendix + checklist).

Upload [`../oir-arxiv.zip`](../oir-arxiv.zip): `main.tex`, `neurips_2026.sty`, `checklist.tex`, the five PNGs used in the TeX, JSON `00README` (`compiler: xelatex`, TeX Live 2025). Do not include `main.pdf` or `fonts/` (arXiv's TeX Live already ships TeX Gyre; `main.tex` falls back to filename lookup). Also select **xelatex** in the upload UI — the dropdown is what AutoTeX actually runs; a hand-written 00README is optional.

Form: primary `cs.CL`; cross-list `cs.AI`. Paste the abstract from `ARXIV_METADATA.txt`. Comments: `9 pages + appendix + checklist, 22 pages total. NeurIPS preprint style. Code: https://github.com/pankajnits/oir/releases/tag/v1.0.5`. License: CC BY 4.0 on the arXiv form (not in the PDF).
