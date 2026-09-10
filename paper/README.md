# Paper

NeurIPS-style preprint (`[preprint]{neurips_2026}`): **11 content pages**, then references and appendix.

| File | Role |
|------|------|
| [`arxiv_upload/main.tex`](arxiv_upload/main.tex) | Source |
| [`arxiv_upload/main.pdf`](arxiv_upload/main.pdf) | Compiled PDF |
| [`oir-arxiv.zip`](oir-arxiv.zip) | arXiv upload (TeX, style, five PNGs, JSON `00README`; **no** PDF, **no** `fonts/`) |
| [`figures/`](figures/) | Figure sources. The arXiv zip includes only the five PNGs referenced in `main.tex` (`fig1`, `fig3`, `fig4`, `fig6`, `fig7`).

Compile:

```bash
cd paper/arxiv_upload
tectonic -X compile main.tex
```

Rebuild figures from locked JSON:

```bash
python3 harness/make_paper_figures.py
cp paper/figures/fig1_matched_2x2.png paper/figures/fig3_dualpath.png \
   paper/figures/fig4_binding.png paper/figures/fig6_rename_equivariance.png \
   paper/figures/fig7_opaque_rel_n200.png paper/arxiv_upload/
```

arXiv form: paste the abstract from [`arxiv_upload/ARXIV_METADATA.txt`](arxiv_upload/ARXIV_METADATA.txt). Primary category `cs.CL`; cross-list `cs.AI`, `cs.LG`. License CC BY 4.0. Upload `oir-arxiv.zip`, not the `arxiv_upload/` folder. JSON `00README` declares `compiler: xelatex` and `texlive_version: 2025`; also select **xelatex** in the processor dropdown (a legacy `00README.XXX` line `xelatex` is not a valid AutoTeX directive). Local `tectonic` still uses `arxiv_upload/fonts/`; the zip omits `fonts/` because TeX Live 2025 already ships those OTFs. Code, quizzes, and scores: https://github.com/pankajnits/oir

Isolation prompts live in `runs/`. Locked scores live in `results/`. See [`../SCIENTIST.md`](../SCIENTIST.md) and [`../bench/README.md`](../bench/README.md).
