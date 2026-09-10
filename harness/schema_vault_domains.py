#!/usr/bin/env python3
"""Schema-visible vault across EHR / ledger / SBOM.

The industrial pattern: relationships (column names / FKs) stay readable;
instance keys and payload cells are sealed. Questions are multi-key joins
(patient_id AND encounter_date; account_id AND txn_id; ghsa AND package).

Arms:
  MILD_PROG  — readable headers, sealed cells, explicit JOIN on named columns
  MILD_NL    — same tables, English question using start seals, no JOIN
  STRICT_PROG — headers AND cells sealed, JOIN over seals
  STRICT_NL  — sealed tables + token-HMAC question, no JOIN

Non-claim: not confidentiality / HIPAA / private-RAG. Seals preserve equality.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "schema_vault_domains"
KEY = b"oir-schema-vault-domains-v1"
SEED = 20260813
OSV_PATH = ROOT / "data" / "osv_advisories_n8.json"


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def shuffle_tables(tables: dict, rng: random.Random) -> dict:
    out = {}
    for name, (headers, rows) in tables.items():
        rows = list(rows)
        rng.shuffle(rows)
        out[name] = (headers, rows)
    return out


def pack(kind: str, header: str, items: list[tuple[str, str]]) -> str:
    tag = "ANSWER_PLAIN" if kind == "plain" else "ANSWER_SEALED"
    hint = "<token_or_UNKNOWN>" if kind == "plain" else "<seal_or_UNKNOWN>"
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. Use CONTEXT only. No decrypt. No world knowledge.",
        f"Format: {tag}[<id>]: {hint}",
        "Answer EVERY ID. If ambiguous, UNKNOWN.",
        "",
        header,
        "",
    ]
    for cid, body in items:
        lines.append(f"##### ID {cid} #####\n{body}\n")
    return "\n".join(lines)


def seal_cell(sealer: EntitySeal, v: str) -> str:
    return sealer.atom(v)


def render_tables(tables: dict[str, tuple[list[str], list[list[str]]]], sealer: EntitySeal | None, *, mild: bool) -> str:
    chunks = []
    for name, (headers, rows) in tables.items():
        if sealer is None:
            h, body = headers, rows
        elif mild:
            h = headers
            body = [[seal_cell(sealer, c) for c in row] for row in rows]
        else:
            h = [seal_cell(sealer, x) for x in headers]
            body = [[seal_cell(sealer, c) for c in row] for row in rows]
        chunks.append(f"TABLE {name}\n" + md_table(h, body))
    return "\n\n".join(chunks)


def ehr_case(i: int, sealer: EntitySeal):
    pid = f"pat-{1000 + i}"
    date = f"2024-03-{10 + i:02d}"
    enc = f"enc-{2000 + i}"
    code = f"SNOMED-{390000 + i}"
    decoy_date = f"2024-06-{10 + i:02d}"
    decoy_enc = f"enc-{3000 + i}"
    decoy_code = f"SNOMED-{490000 + i}"
    other = f"pat-{8000 + i}"
    other_enc = f"enc-{9000 + i}"
    other_code = f"SNOMED-{590000 + i}"
    tables = {
        "patients": (
            ["patient_id", "birth_year"],
            [[pid, str(1960 + i)], [other, str(1975 + i)]],
        ),
        "encounters": (
            ["enc_id", "patient_id", "encounter_date", "practitioner_id"],
            [
                [enc, pid, date, f"prac-{i}"],
                [decoy_enc, pid, decoy_date, f"prac-{i}-b"],  # same patient, other date
                [other_enc, other, date, f"prac-{i}-c"],  # same date, other patient
            ],
        ),
        "conditions": (
            ["enc_id", "condition_code", "status"],
            [
                [enc, code, "active"],
                [decoy_enc, decoy_code, "resolved"],
                [other_enc, other_code, "active"],
            ],
        ),
    }
    join = (
        "JOIN_QUERY (composite key)\n"
        f"K1 patient_id = {pid}\n"
        f"K2 encounter_date = {date}\n"
        "JOIN encounters.patient_id = patients.patient_id\n"
        "JOIN conditions.enc_id = encounters.enc_id\n"
        "Filter encounters.encounter_date = K2; return conditions.condition_code."
    )
    q = (
        f"What is the condition_code for patient {pid} on encounter_date {date}? "
        "Use both keys; other encounters for this patient must not be used."
    )
    return {
        "domain": "EHR",
        "schema": "FHIR-shaped synthetic Patient/Encounter/Condition (not real PHI)",
        "keys": ["patient_id", "encounter_date"],
        "gold": code,
        "join_plain": join,
        "q_plain": q,
        "tables": tables,
        "atoms_in_join": [pid, date],
    }


def ledger_case(i: int, sealer: EntitySeal):
    acct = f"acct-{4000 + i}"
    txn = f"txn-{5000 + i}"
    merch = f"mid-{6000 + i}"
    city = f"MCC-city-{i}"
    other_txn = f"txn-{5100 + i}"
    other_merch = f"mid-{6100 + i}"
    other_city = f"MCC-city-X{i}"
    other_acct = f"acct-{4100 + i}"
    tables = {
        "accounts": (
            ["account_id", "kyc_tier"],
            [[acct, "T2"], [other_acct, "T1"]],
        ),
        "transactions": (
            ["txn_id", "account_id", "merchant_id", "amount"],
            [
                [txn, acct, merch, str(1200 + i)],
                [other_txn, acct, other_merch, str(50 + i)],  # same account, other txn
                [f"txn-z{i}", other_acct, merch, "9"],
            ],
        ),
        "merchants": (
            ["merchant_id", "mcc", "merchant_city"],
            [[merch, "5411", city], [other_merch, "5812", other_city]],
        ),
    }
    join = (
        "JOIN_QUERY (composite key)\n"
        f"K1 account_id = {acct}\n"
        f"K2 txn_id = {txn}\n"
        "JOIN transactions.account_id = accounts.account_id\n"
        "JOIN merchants.merchant_id = transactions.merchant_id\n"
        "Filter transactions.txn_id = K2; return merchants.merchant_city."
    )
    q = (
        f"What is the merchant_city for account {acct} and txn {txn}? "
        "Both keys required; other txns on this account are distractors."
    )
    return {
        "domain": "LEDGER",
        "schema": "AML-shaped account/transaction/merchant (synthetic)",
        "keys": ["account_id", "txn_id"],
        "gold": city,
        "join_plain": join,
        "q_plain": q,
        "tables": tables,
        "atoms_in_join": [acct, txn],
    }


def osv_case(i: int, rec: dict):
    ghsa, pkg, cve, eco = rec["id"], rec["package"], rec["cve"], rec["ecosystem"]
    other = f"GHSA-decoy-{i:04d}"
    other_cve = f"CVE-2099-{1000 + i}"
    other_pkg = f"decoy-pkg-{i}"
    tables = {
        "advisories": (
            ["ghsa_id", "package", "ecosystem", "cve_alias"],
            [
                [ghsa, pkg, eco, cve],
                [other, pkg, eco, other_cve],  # same package, other advisory
                [f"GHSA-otherpkg-{i}", other_pkg, eco, f"CVE-2098-{i}"],
            ],
        ),
        "packages": (
            ["package", "ecosystem", "registry"],
            [[pkg, eco, eco], [other_pkg, eco, eco]],
        ),
    }
    join = (
        "JOIN_QUERY (composite key)\n"
        f"K1 ghsa_id = {ghsa}\n"
        f"K2 package = {pkg}\n"
        "JOIN packages.package = advisories.package\n"
        "Filter advisories.ghsa_id = K1 AND advisories.package = K2; return cve_alias."
    )
    q = (
        f"What cve_alias is recorded for advisory {ghsa} affecting package {pkg}? "
        "Both keys required."
    )
    return {
        "domain": "SBOM",
        "schema": "OSV.dev advisory JSON flattened (CC-BY-4.0); gold CVE is dataset fact",
        "keys": ["ghsa_id", "package"],
        "gold": cve,
        "join_plain": join,
        "q_plain": q,
        "tables": tables,
        "atoms_in_join": [ghsa, pkg],
        "source_id": ghsa,
    }


def seal_join(join: str, sealer: EntitySeal, atoms: list[str]) -> str:
    body = join
    for a in sorted(set(atoms), key=len, reverse=True):
        body = body.replace(a, sealer.atom(a))
    # also seal column names in STRICT by replacing after mild? handled separately
    return body


def seal_headers_in_join(join: str, sealer: EntitySeal, headers: list[str]) -> str:
    body = join
    for h in sorted(set(headers), key=len, reverse=True):
        body = body.replace(h, sealer.atom(h))
    return body


def all_headers(tables) -> list[str]:
    out = []
    for _, (h, _) in tables.items():
        out.extend(h)
    return out


def build():
    sealer = EntitySeal(KEY)
    rng = random.Random(SEED)
    osv = json.loads(OSV_PATH.read_text())["items"]
    osv_pick = [osv[0], osv[3], osv[6], osv[7]]
    specs = [ehr_case(i, sealer) for i in range(4)]
    specs += [ledger_case(i, sealer) for i in range(4)]
    specs += [osv_case(i, osv_pick[i]) for i in range(4)]
    assert len(specs) == 12

    buckets = {k: [] for k in ("MILD_PROG", "MILD_NL", "STRICT_PROG", "STRICT_NL")}
    cases = []
    for i, spec in enumerate(specs):
        spec["tables"] = shuffle_tables(spec["tables"], rng)
        gold_seal = sealer.atom(spec["gold"])
        headers = all_headers(spec["tables"])
        ret_name = {"EHR": "conditions", "LEDGER": "merchants", "SBOM": "advisories"}[spec["domain"]]
        ret_col = {"EHR": "condition_code", "LEDGER": "merchant_city", "SBOM": "cve_alias"}[spec["domain"]]
        for _ in range(20):
            rh, rrows = spec["tables"][ret_name]
            ci = rh.index(ret_col)
            gold_first = rrows[0][ci] == spec["gold"]
            if not gold_first:
                break
            spec["tables"] = shuffle_tables(spec["tables"], rng)
        rh, rrows = spec["tables"][ret_name]
        ci = rh.index(ret_col)
        gold_first = rrows[0][ci] == spec["gold"]
        mild_tbl = render_tables(spec["tables"], sealer, mild=True)
        strict_tbl = render_tables(spec["tables"], sealer, mild=False)
        join_mild = seal_join(spec["join_plain"], sealer, spec["atoms_in_join"])
        join_strict = seal_headers_in_join(join_mild, sealer, headers)

        q_mild = spec["q_plain"]
        for a in spec["atoms_in_join"]:
            q_mild = q_mild.replace(a, sealer.atom(a))
        q_strict = sealer.text(spec["q_plain"])

        ids = {
            "MILD_PROG": f"SV_MILDPROG_{i}",
            "MILD_NL": f"SV_MILDNL_{i}",
            "STRICT_PROG": f"SV_STRICTPROG_{i}",
            "STRICT_NL": f"SV_STRICTNL_{i}",
        }
        buckets["MILD_PROG"].append(
            (ids["MILD_PROG"], f"{join_mild}\n\nCONTEXT:\n{mild_tbl}")
        )
        buckets["MILD_NL"].append(
            (ids["MILD_NL"], f"QUESTION:\n{q_mild}\n\nCONTEXT:\n{mild_tbl}")
        )
        buckets["STRICT_PROG"].append(
            (ids["STRICT_PROG"], f"{join_strict}\n\nCONTEXT:\n{strict_tbl}")
        )
        buckets["STRICT_NL"].append(
            (ids["STRICT_NL"], f"QUESTION:\n{q_strict}\n\nCONTEXT:\n{strict_tbl}")
        )
        cases.append(
            {
                "i": i,
                "domain": spec["domain"],
                "keys": spec["keys"],
                "gold": spec["gold"],
                "expect_seal": gold_seal,
                "ids": ids,
                "schema": spec["schema"],
                "question": spec["q_plain"],
                "source_id": spec.get("source_id"),
                "gold_is_first_return_row": gold_first,
            }
        )

    RUNS.mkdir(parents=True, exist_ok=True)
    headers = {
        "MILD_PROG": "ARM MILD_PROG: readable column names (schema known), sealed cells, JOIN on named columns + composite keys.",
        "MILD_NL": "ARM MILD_NL: readable columns, sealed cells, English question with start-ID seals. No JOIN program.",
        "STRICT_PROG": "ARM STRICT_PROG: sealed headers AND cells + JOIN over seals.",
        "STRICT_NL": "ARM STRICT_NL: sealed headers/cells + token-HMAC question. No JOIN.",
    }
    paths = {}
    kinds = {"MILD_PROG": "sealed", "MILD_NL": "sealed", "STRICT_PROG": "sealed", "STRICT_NL": "sealed"}
    for arm, items in buckets.items():
        d = RUNS / f"{arm}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack("sealed", headers[arm], items))
        paths[arm] = str(p)

    harness = {
        "n": 12,
        "seed": SEED,
        "suite": "schema_vault_domains",
        "domains": ["EHR", "LEDGER", "SBOM"],
        "prediction": "MILD_PROG ≈ STRICT_PROG ≫ STRICT_NL; MILD_NL tests whether readable schema is enough without JOIN",
        "nonclaim": (
            "Not HIPAA/AML/privacy solved. EHR/ledger rows are synthetic. "
            "OSV CVE golds are public facts; sealing is a capability control. "
            "Not G-Rev1 (gold JOIN in PROG arms)."
        ),
        "paths": paths,
        "cases": cases,
        "what_is_sealed": {
            "MILD_*": "cell values / instance IDs; column names readable",
            "STRICT_*": "headers + cells; STRICT_NL also token-HMACs the question",
        },
        "what_is_asked": "composite-key 2-table joins (2 keys required; distractor rows share one key)",
        "what_is_checked": "HMAC of gold cell (condition_code / merchant_city / cve_alias)",
    }
    out = RESULTS / "schema_vault_domains_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": 12, "domains": {"EHR": 4, "LEDGER": 4, "SBOM": 4}, "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
