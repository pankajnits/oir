# Named preprint source

This folder stays in the repo. It is the NeurIPS-style science source, not the public PDF.

- Public PDF: [`../zenodo/main.pdf`](../zenodo/main.pdf)
- Anonymous review PDF + zip: [`../tmlr/`](../tmlr/)
- This folder: named TeX (author, GitHub, NeurIPS checklist)

Compile a named PDF only when you want one:

```bash
tectonic -X compile main.tex
```

arXiv later still needs a `cs.CL` endorsement if you have not posted there before. The public PDF is `paper/zenodo/main.pdf`. Do not upload `main.pdf` from here to OpenReview.
