# Paper

NeurIPS-style preprint (`[preprint]{neurips_2026}`): **9 content pages**, then references and appendix.

| File | Role |
|------|------|
| [`arxiv_upload/main.tex`](arxiv_upload/main.tex) | Source |
| [`arxiv_upload/main.pdf`](arxiv_upload/main.pdf) | Compiled PDF |
| [`oir-arxiv.zip`](oir-arxiv.zip) | arXiv upload (TeX, style, fonts, figures; **no** PDF) |
| [`figures/`](figures/) | Figure sources (copied into `arxiv_upload/` for the zip) |

Compile:

```bash
cd paper/arxiv_upload
tectonic -X compile main.tex
```

Rebuild figures from locked JSON:

```bash
python3 harness/make_paper_figures.py
cp paper/figures/fig*.png paper/arxiv_upload/
```

arXiv form: paste the abstract from [`arxiv_upload/ARXIV_METADATA.txt`](arxiv_upload/ARXIV_METADATA.txt). Primary category `cs.CL`; cross-list `cs.AI`, `cs.LG`. License CC BY 4.0. Upload `oir-arxiv.zip`, not the `arxiv_upload/` folder. `00README.XXX` requests `xelatex`. Code, quizzes, and scores: https://github.com/pankajnits/oir

Isolation prompts live in `runs/`. Locked scores live in `results/`. See [`../SCIENTIST.md`](../SCIENTIST.md) and [`../bench/README.md`](../bench/README.md).
