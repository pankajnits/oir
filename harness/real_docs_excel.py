#!/usr/bin/env python3
"""
Real-document OIR pilot: Excel (and PDF export) → sealed NL vs PATH_PROG.

Workbook A (fully real entities): Wikidata CEO→company→HQ as Excel sheets.
Workbook B (real registry): OpenData500 companies + synthetic staff roster
  (documented: real firms, synthetic employees for 2-hop joins).

Produces isolated MUT batches under runs/real_docs/.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from nl_to_path_compiler import PathCompiler  # noqa: E402
from seal_router import SealRouter  # noqa: E402

try:
    from openpyxl import Workbook
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl", "-q"])
    from openpyxl import Workbook

DATA_DIR = ROOT / "data" / "real_docs"
RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "real_docs"
WIKI = json.loads((ROOT / "data/real/wikidata_ceo_hops_v2.json").read_text())
OD500 = DATA_DIR / "opendata500_us_companies.csv"
KEY = b"oir-real-docs-excel-v1"
SEED = 20260727
N = 16


class EntitySeal:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def atom(self, a: str) -> str:
        a = re.sub(r"\s+", "_", a.strip())
        if a not in self.fwd:
            d = hmac.new(self.key, a.encode(), hashlib.sha256).digest()
            t = "E" + d[:6].hex()
            self.fwd[a] = t
            self.rev[t] = a
        return self.fwd[a]

    def text(self, s: str) -> str:
        return "".join(
            self.atom(p) if re.fullmatch(r"[A-Za-z0-9_]+", p) else p
            for p in re.findall(r"[A-Za-z0-9_]+|[^A-Za-z0-9_]+", s)
        )


def atomize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def write_xlsx(path: Path, sheets: dict[str, list[list]]):
    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title[:31])
        for row in rows:
            ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def build_wiki_excel():
    """Real people/companies/HQ from Wikidata → Employees + Companies sheets."""
    pool = []
    seen = set()
    for r in WIKI:
        if r["person"] in seen or re.match(r"^Q\d+$", r["person"]):
            continue
        seen.add(r["person"])
        pool.append(r)
    rng = random.Random(SEED)
    rng.shuffle(pool)
    quiz = pool[:N]

    emp_rows = [["Employee", "Company", "Role"]]
    co_rows = [["Company", "HQ_City", "Country"]]
    cos_seen = set()
    for r in quiz:
        emp_rows.append([r["person"].replace("_", " "), r["company"].replace("_", " "), "CEO"])
        if r["company"] not in cos_seen:
            cos_seen.add(r["company"])
            co_rows.append([r["company"].replace("_", " "), r["hq"].replace("_", " "), "US/EU"])

    # distractor companies
    for r in pool[N : N + 8]:
        if r["company"] not in cos_seen:
            cos_seen.add(r["company"])
            co_rows.append([r["company"].replace("_", " "), r["hq"].replace("_", " "), "US/EU"])

    path = DATA_DIR / "wiki_ceo_hr.xlsx"
    write_xlsx(path, {"Employees": emp_rows, "Companies": co_rows})
    return path, quiz


def build_od500_excel():
    """Real OpenData500 firms + synthetic employees (documented)."""
    rows = list(csv.DictReader(OD500.open()))
    usable = [
        r
        for r in rows
        if r.get("company_name") and r.get("city") and r.get("company_category") == "Data/Technology"
    ]
    rng = random.Random(SEED + 1)
    rng.shuffle(usable)
    firms = usable[:N]

    # synthetic first names + last names (not claiming real people)
    first = ["Alex", "Jordan", "Sam", "Taylor", "Casey", "Riley", "Morgan", "Avery", "Quinn", "Reese", "Jamie", "Drew", "Cameron", "Harper", "Rowan", "Parker"]
    last = ["Nguyen", "Patel", "Garcia", "Kim", "Brown", "Silva", "Cohen", "Okoro", "Ivanov", "Sato", "Andersen", "Costa", "Berg", "Ali", "Walsh", "Diaz"]

    emp_rows = [["Employee", "Company", "Role"]]
    co_rows = [["Company", "HQ_City", "State", "Category", "Source"]]
    quiz = []
    for i, r in enumerate(firms):
        person = f"{first[i]} {last[i]}"
        company = r["company_name"]
        hq = r["city"]
        emp_rows.append([person, company, "Account_Lead"])
        co_rows.append([company, hq, r.get("state", ""), r["company_category"], "OpenData500"])
        quiz.append(
            {
                "person": atomize(person),
                "company": atomize(company),
                "hq": atomize(hq),
                "person_display": person,
                "company_display": company,
                "hq_display": hq,
            }
        )

    path = DATA_DIR / "opendata500_staff.xlsx"
    write_xlsx(path, {"Employees": emp_rows, "Companies": co_rows})
    meta = {
        "source": "https://github.com/GovLab/OpenData500",
        "license_note": "OpenData500 US companies CSV; employee names synthetic for join tasks",
        "n_firms": len(firms),
    }
    (DATA_DIR / "opendata500_staff_meta.json").write_text(json.dumps(meta, indent=2))
    return path, quiz


def excel_to_edges(quiz_row, all_quiz, decoy, ambiguous=True):
    """Build sealed-context edges from spreadsheet semantics (+ distractors)."""
    person, company, hq = quiz_row["person"], quiz_row["company"], quiz_row["hq"]
    dco, dhq = decoy["company"], decoy["hq"]
    edges = [
        (person, "works_at", company),
        (company, "headquartered_in", hq),
        (dco, "headquartered_in", dhq),
    ]
    if ambiguous:
        hold, part = f"Hold_{company}", f"Partner_{company}"
        edges += [
            (company, "owned_by", hold),
            (hold, "meta_of", f"Meta_{company}"),
            (company, "partner_of", part),
            (part, "meta_of", f"PMeta_{company}"),
            (f"DecoyPerson_{dco}", "works_at", dco),
        ]
    return edges


def render(sealer, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h, r, t in edges)


def write_batch(name, header, items):
    d = RUNS / f"{name}_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "Context was extracted from a real Excel workbook then sealed.\n",
        "Same encoding on question and context. No external world knowledge.\n",
        "Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
        header + "\n",
    ]
    for cid, body in items:
        lines.append(f"\n##### ID {cid} #####\n{body}\n")
    (d / "BATCH.txt").write_text("\n".join(lines))
    return str(d / "BATCH.txt")


def make_pdf_from_xlsx_note(xlsx_path: Path):
    """Minimal PDF: textual dump of sheet rows (table-as-PDF transfer)."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None
    pdf_path = xlsx_path.with_suffix(".pdf.txt")  # plain transfer artifact if no reportlab
    wb = load_workbook(xlsx_path, read_only=True)
    chunks = [f"PDF-TRANSFER of {xlsx_path.name} (sheet text dump for OIR)\n"]
    for name in wb.sheetnames:
        chunks.append(f"\n== Sheet: {name} ==\n")
        for row in wb[name].iter_rows(values_only=True):
            chunks.append("\t".join("" if c is None else str(c) for c in row) + "\n")
    pdf_path.write_text("".join(chunks))
    # try real PDF
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas as pdfcanvas

        real_pdf = xlsx_path.with_suffix(".pdf")
        c = pdfcanvas.Canvas(str(real_pdf), pagesize=letter)
        y = 750
        c.setFont("Helvetica", 9)
        for line in "".join(chunks).splitlines()[:80]:
            c.drawString(40, y, line[:95])
            y -= 12
            if y < 40:
                c.showPage()
                c.setFont("Helvetica", 9)
                y = 750
        c.save()
        return real_pdf
    except Exception:
        return pdf_path


def suite(tag: str, quiz: list, xlsx_path: Path):
    rng = random.Random(SEED + hash(tag) % 1000)
    sealer = EntitySeal(KEY + tag.encode())
    for r in ("works_at", "headquartered_in", "owned_by", "partner_of", "meta_of"):
        sealer.atom(r)
    lexicon = {r["person"] for r in quiz}
    # also allow display forms with spaces → atomize
    compiler = PathCompiler(lexicon)

    nl_items, prog_items = [], []
    cases = []
    for i, row in enumerate(quiz):
        decoy = rng.choice([r for r in quiz if r["company"] != row["company"]])
        edges = excel_to_edges(row, quiz, decoy)
        rng.shuffle(edges)
        ctx = render(sealer, edges)
        person_disp = row.get("person_display", row["person"].replace("_", " "))
        nl = f"Where is the company headquartered that {person_disp} works at?"
        # compile with atom person
        cr = compiler.compile(
            f"Where is the company headquartered_in that {row['person']} works_at?"
        )
        assert cr.ok, (nl, cr)
        exp = sealer.atom(row["hq"])
        mid = sealer.atom(row["company"])
        prog = (
            f"PATH_QUERY\nSTART {sealer.atom(row['person'])}\n"
            f"R1 {sealer.atom('works_at')}\nR2 {sealer.atom('headquartered_in')}\n"
            f"Execute START -R1-> x -R2-> y. Return y seal only."
        )
        # router bound
        triples = [(sealer.atom(h), sealer.atom(r), sealer.atom(t)) for h, r, t in edges]
        assert list(dict.fromkeys(SealRouter(triples).path(
            sealer.atom(row["person"]), [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        ))) == [exp]

        cid_n = f"XD_{tag}_NL_{i}"
        cid_p = f"XD_{tag}_PROG_{i}"
        # seal NL with underscore person for even, spaces odd — prefer underscore for fair atom match
        nl_for_seal = f"Where is the company headquartered_in that {row['person']} works_at?"
        nl_items.append((cid_n, f"SOURCE: {xlsx_path.name}\nQUESTION:\n{sealer.text(nl_for_seal)}\n\nCONTEXT:\n{ctx}"))
        prog_items.append((cid_p, f"SOURCE: {xlsx_path.name}\n{prog}\n\nCONTEXT:\n{ctx}"))
        cases.append(
            {
                "id": cid_n,
                "form": "NL",
                "tag": tag,
                "expect": exp,
                "intermediate_company": mid,
                "person": row["person"],
                "hq": row["hq"],
                "xlsx": xlsx_path.name,
            }
        )
        cases.append(
            {
                "id": cid_p,
                "form": "PROG",
                "tag": tag,
                "expect": exp,
                "intermediate_company": mid,
                "person": row["person"],
                "hq": row["hq"],
                "xlsx": xlsx_path.name,
            }
        )

    p_nl = write_batch(f"{tag}_NL", f"REAL EXCEL [{tag}] sealed NL questions.", nl_items)
    p_pr = write_batch(f"{tag}_PROG", f"REAL EXCEL [{tag}] sealed PATH_QUERY.", prog_items)
    return cases, {"NL": p_nl, "PROG": p_pr}, sealer.rev


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wiki_xlsx, wiki_quiz = build_wiki_excel()
    # normalize wiki quiz keys
    wiki_quiz = [
        {
            "person": r["person"],
            "company": r["company"],
            "hq": r["hq"],
            "person_display": r["person"].replace("_", " "),
            "company_display": r["company"].replace("_", " "),
            "hq_display": r["hq"].replace("_", " "),
        }
        for r in wiki_quiz
    ]
    od_xlsx, od_quiz = build_od500_excel()
    wiki_pdf = make_pdf_from_xlsx_note(wiki_xlsx)

    cases_w, paths_w, rev_w = suite("WIKI_XLSX", wiki_quiz, wiki_xlsx)
    cases_o, paths_o, rev_o = suite("OD500_XLSX", od_quiz, od_xlsx)

    harness = {
        "protocol": "REAL_DOCS_PROTOCOL.md",
        "n_per_suite": N,
        "workbooks": {
            "wiki": str(wiki_xlsx),
            "opendata500": str(od_xlsx),
            "wiki_pdf_transfer": str(wiki_pdf) if wiki_pdf else None,
        },
        "paths": {**paths_w, **{f"OD_{k}": v for k, v in paths_o.items()}},
        "cases": cases_w + cases_o,
        "rev": {**rev_w, **rev_o},
        "claim": "Same NL≪PROG dissociation on Excel-extracted sealed context",
    }
    # fix paths keys
    harness["paths"] = {
        "WIKI_NL": paths_w["NL"],
        "WIKI_PROG": paths_w["PROG"],
        "OD500_NL": paths_o["NL"],
        "OD500_PROG": paths_o["PROG"],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "real_docs_excel_harness.json").write_text(json.dumps(harness, indent=2))
    print(
        json.dumps(
            {
                "wiki_xlsx": str(wiki_xlsx),
                "od500_xlsx": str(od_xlsx),
                "pdf": str(wiki_pdf) if wiki_pdf else None,
                "n_cases": len(harness["cases"]),
                "batches": harness["paths"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
