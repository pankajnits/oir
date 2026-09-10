# arXiv source

Compiled PDF: [`main.pdf`](main.pdf) (11 content pages + references + appendix).

Upload [`../oir-arxiv.zip`](../oir-arxiv.zip): `main.tex`, `neurips_2026.sty`, the five PNGs used in the TeX, JSON `00README` (`compiler: xelatex`, TeX Live 2025). Do not include `main.pdf` or `fonts/` (arXiv's TeX Live already ships TeX Gyre; `main.tex` falls back to filename lookup). Also select **xelatex** in the upload UI — the JSON file is the in-archive record, the dropdown is what AutoTeX actually runs.

Form: primary `cs.CL`; cross-list `cs.AI`, `cs.LG`. Paste the abstract from `ARXIV_METADATA.txt`. Comments: `11 pages + appendix, 20 pages total. NeurIPS preprint style. Code: https://github.com/pankajnits/oir`. License: CC BY 4.0 on the arXiv form (not in the PDF).
