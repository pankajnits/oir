# Paper

Two copies of the same science TeX, for two jobs.

| Path | Role |
|------|------|
| [`tmlr/`](tmlr/) | **TMLR review upload.** Anonymous PDF (`main.pdf`) and `oir-tmlr-supplementary.zip`. Header: “Under review as submission to TMLR.” Do not put GitHub on the OpenReview form. |
| [`arxiv_upload/`](arxiv_upload/) | **Named preprint source.** Keep this folder. It is not the OpenReview package. Compile here only when you want a named PDF. |

Science source is `arxiv_upload/main.tex`. The TMLR file is built from it:

```bash
python3 paper/tmlr/convert_from_arxiv.py
cd paper/tmlr && tectonic -X compile main.tex
python3 paper/tmlr/build_supplementary.py
```

That zip excludes `paper/`, `CITATION.cff`, `.git/`, and PDFs. Upload only `paper/tmlr/main.pdf` and `paper/tmlr/oir-tmlr-supplementary.zip`.

Named preprint later (endorsement is a separate arXiv account issue):

```bash
cd paper/arxiv_upload
tectonic -X compile main.tex
```

Rebuild figures from locked JSON (`make_paper_figures.py` also copies the PNGs into `paper/arxiv_upload/`):

```bash
python3 harness/make_paper_figures.py
```

Isolation prompts live in `runs/`. Locked scores live in `results/`. See [`../SCIENTIST.md`](../SCIENTIST.md) and [`../bench/README.md`](../bench/README.md).
