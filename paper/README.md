# Paper

Science TeX is `arxiv_upload/main.tex`. Three builds come from it.

| Path | Role |
|------|------|
| [`zenodo/`](zenodo/) | **Public preprint.** Named PDF (`oir-preprint.pdf`), TMLR style, no NeurIPS checklist. Rebuild with `python3 paper/zenodo/build.py`. |
| [`arxiv_upload/`](arxiv_upload/) | **NeurIPS-style source.** Author, GitHub, and the NeurIPS checklist. This is the arXiv source bundle, not the public PDF. |
| [`tmlr/`](tmlr/) | **Anonymous review files.** `main.pdf` and `oir-tmlr-supplementary.zip`. Header: “Under review as submission to TMLR.” |

The TMLR review file is built from the science TeX:

```bash
python3 paper/tmlr/convert_from_arxiv.py
cd paper/tmlr && tectonic -X compile main.tex
python3 paper/tmlr/build_supplementary.py
```

That zip excludes `paper/`, `CITATION.cff`, `.git/`, and PDFs. It is the anonymous review archive, not the public PDF.

Public PDF:

```bash
python3 paper/zenodo/build.py
```

NeurIPS-style PDF (checklist included; arXiv still needs a `cs.CL` endorsement):

```bash
cd paper/arxiv_upload
tectonic -X compile main.tex
```

Rebuild figures from locked JSON (`make_paper_figures.py` also copies the PNGs into `paper/arxiv_upload/`):

```bash
python3 harness/make_paper_figures.py
```

Isolation prompts live in `runs/`. Locked scores live in `results/`. See [`../SCIENTIST.md`](../SCIENTIST.md) and [`../bench/README.md`](../bench/README.md).
