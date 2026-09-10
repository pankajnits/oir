#!/usr/bin/env python3
"""
Subjective / opaque-generation harness.

GOAL (locked): prove find + generate over sealed Q+C — without gold answer lines
and without a cleartext system that reads Q/C to pick evidence.

Conditions
----------
  NL            — full sealed CONTEXT; free sealed answer (control)
  EVIDENCE      — LLM must pick spans itself then answer (soft, no gold)
  SEAL_RETRIEVE — opaque finder: rank CONTEXT lines by sealed-token overlap
                  with QUESTION (IDF-weighted). LLM sees ONLY top-k sealed
                  lines + sealed Q. No plaintext. No gold.
  EV_HANDLES    — DIAGNOSTIC ONLY (oracle gold spans). Not the claim.

Score: evidence recall vs gold (post-hoc) + unsealed rubric. Harness unseals only.
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oir import EntitySeal  # noqa: E402

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "subjective"
FETA = ROOT / "data" / "benchmarks" / "FeTaQA" / "feta_sample.jsonl"
KEY = b"oir-subjective-v1"
SEED = 20260728
TOP_K = 6
SEAL_RE = re.compile(r"E[0-9a-f]{12}")

# Lexical legend (plaintext only at build). MUT may see sealed SYN lines.
# Not gold answer lines — same role as relation handles for paraphrase.
SYN_GROUPS = [
    ["keep", "kept", "retain", "retained", "retention"],
    ["leave", "pto", "absence"],
    ["password", "login", "sign_in"],
    ["lock", "locked"],
    ["safe", "safest", "secure", "security"],
    ["where", "location", "processed", "transfer", "geographically"],
    ["close", "closure", "closed"],
    ["data", "information", "record", "profile"],
    ["admin", "administrator"],
    ["fail", "failed", "failing"],
    ["long", "month", "year", "day", "retain"],
]


def prep_for_seal(s: str) -> str:
    """Uniform string prep before seal (not a cleartext 'reader').

    Lowercase + light singularize so isomorphic overlap survives Primary/primary
    and caregiver/caregivers. Applied identically to Q and C — no gold selection.
    """

    def one(m: re.Match) -> str:
        w = m.group(0).lower()
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        return w

    return re.sub(r"[A-Za-z0-9_.\-]+", one, s)


def seal_text(sealer: EntitySeal, s: str) -> str:
    return sealer.text(prep_for_seal(s))

DOCS = {
    "privacy_policy": """
ACME CLOUD PRIVACY POLICY
Effective date: January 15, 2025
Last updated: June 1, 2025

1. Who we are
Acme Cloud Inc. ("Acme") provides hosted project management software.

2. Data we collect
We collect account email, name, billing address, and usage telemetry.
We do not sell personal data to third parties.

3. Retention
Account profile data is retained for 24 months after account closure.
Billing records are retained for 7 years for tax compliance.
Support chat transcripts are retained for 90 days.

4. International transfers
Customer data may be processed in the United States and Germany.
Standard Contractual Clauses apply for EEA customers.

5. Contact
Privacy requests: privacy@acmecloud.example
Response SLA: 30 calendar days.
""".strip(),
    "hr_handbook": """
NORTHWIND EMPLOYEE HANDBOOK — TIME OFF
Version 4.2 | Applies to full-time US employees

Paid Time Off (PTO)
- Full-time employees accrue 20 days of PTO per calendar year.
- Part-time employees accrue PTO proportional to hours worked.
- Unused PTO up to 5 days may roll over; excess is forfeited on January 1.

Sick leave
- Separate from PTO: 6 sick days per year.
- Doctor's note required for absences longer than 3 consecutive days.

Parental leave
- Primary caregivers: 12 weeks paid parental leave.
- Secondary caregivers: 4 weeks paid parental leave.

Blackout dates
- No PTO is approved during the annual inventory week (first full week of December),
  except for documented emergencies approved by a VP.
""".strip(),
    "support_kb": """
HELP CENTER — Password & Sign-in (Acme Cloud)

Resetting your password
1. Open https://app.acmecloud.example/login
2. Click "Forgot password"
3. Enter the email on the account
4. Open the reset link within 20 minutes
5. Choose a new password with at least 12 characters

If you do not receive the email
- Check spam/junk
- Confirm you are using the work email on the account
- SSO users must reset through their company identity provider, not this form

Locked accounts
- After 5 failed attempts, the account locks for 30 minutes.
- Admins can unlock immediately from Admin > Users > Security.

Two-factor authentication
- 2FA is required for all admin roles.
- Supported methods: authenticator app and hardware security key.
- SMS 2FA was deprecated on March 1, 2025.
""".strip(),
}

SUBJECTIVE_CASES = [
    {
        "id": "SUB_HR_0",
        "doc": "hr_handbook",
        "question": (
            "I'm about to become a primary caregiver — what leave should I plan for, "
            "and is it better than secondary caregiver leave?"
        ),
        "gold_evidence_plain": [
            "Primary caregivers: 12 weeks paid parental leave.",
            "Secondary caregivers: 4 weeks paid parental leave.",
        ],
        "rubric_must": ["12", "primary", "4", "secondary"],
        "note": "comparative advice; both facts required",
    },
    {
        "id": "SUB_HR_1",
        "doc": "hr_handbook",
        "question": (
            "What are my realistic options if I want time off in early December "
            "— should I even try?"
        ),
        "gold_evidence_plain": [
            "No PTO is approved during the annual inventory week (first full week of December),",
            "except for documented emergencies approved by a VP.",
        ],
        "rubric_must": ["december", "inventory", "emergency", "vp"],
    },
    {
        "id": "SUB_SUP_0",
        "doc": "support_kb",
        "question": (
            "As an admin, what's the safest way to do 2FA nowadays — is SMS still okay?"
        ),
        "gold_evidence_plain": [
            "Supported methods: authenticator app and hardware security key.",
            "SMS 2FA was deprecated on March 1, 2025.",
            "2FA is required for all admin roles.",
        ],
        "rubric_must": ["authenticator", "deprecated", "sms"],
    },
    {
        "id": "SUB_SUP_1",
        "doc": "support_kb",
        "question": (
            "I keep failing login — summarize what happens and what an admin can do for me."
        ),
        "gold_evidence_plain": [
            "After 5 failed attempts, the account locks for 30 minutes.",
            "Admins can unlock immediately from Admin > Users > Security.",
        ],
        "rubric_must": ["5", "30", "admin", "unlock"],
    },
    {
        "id": "SUB_PRIV_0",
        "doc": "privacy_policy",
        "question": (
            "If I close my account, how long do you keep different kinds of my data "
            "— give a clear summary."
        ),
        "gold_evidence_plain": [
            "Account profile data is retained for 24 months after account closure.",
            "Billing records are retained for 7 years for tax compliance.",
            "Support chat transcripts are retained for 90 days.",
        ],
        "rubric_must": ["24", "7", "90"],
    },
    {
        "id": "SUB_PRIV_1",
        "doc": "privacy_policy",
        "question": (
            "Where might my data go geographically, and what protects EEA customers?"
        ),
        "gold_evidence_plain": [
            "Customer data may be processed in the United States and Germany.",
            "Standard Contractual Clauses apply for EEA customers.",
        ],
        "rubric_must": ["united", "germany", "eea"],
    },
]


def table_to_text(table_array: list) -> str:
    return "\n".join(" | ".join(str(c) for c in row) for row in table_array[:12])


def load_feta(n: int, rng: random.Random) -> list[dict]:
    if not FETA.exists():
        return []
    rows = [json.loads(l) for l in FETA.read_text().splitlines() if l.strip()]
    rng.shuffle(rows)
    out = []
    for r in rows:
        q = r.get("question") or ""
        a = r.get("answer") or ""
        table = r.get("table_array") or []
        if len(q) < 20 or len(a) < 20 or len(table) < 2:
            continue
        title = r.get("table_page_title") or r.get("table_section_title") or "table"
        evid = [title]
        for tok in re.findall(r"[A-Za-z0-9]{4,}", a):
            for row in table:
                line = " | ".join(str(c) for c in row)
                if tok in line and line not in evid:
                    evid.append(line)
                    break
            if len(evid) >= 3:
                break
        out.append(
            {
                "id": f"FETA_{r.get('feta_id', len(out))}",
                "doc": "feta",
                "question": q,
                "gold_answer_plain": a,
                "gold_evidence_plain": evid[:3],
                "context_plain": f"{title}\n{table_to_text(table)}\n",
                "rubric_must": [t.lower() for t in re.findall(r"[A-Za-z0-9]{5,}", a)[:4]],
                "note": "FeTaQA free-form table answer",
            }
        )
        if len(out) >= n:
            break
    return out


def seal_tokens(s: str) -> set[str]:
    return set(SEAL_RE.findall(s))


def expand_query_seals(sealer: EntitySeal, q_sealed: str, q_plain: str) -> set[str]:
    """Expand query seals with sealed synonym mates. No gold CONTEXT lines."""
    toks = set(seal_tokens(q_sealed))
    words = set(re.findall(r"[a-z0-9_.\-]+", prep_for_seal(q_plain).lower()))
    for group in SYN_GROUPS:
        if words & set(group):
            for w in group:
                toks.add(sealer.atom(prep_for_seal(w)))
    return toks


def sealed_syn_legend(sealer: EntitySeal) -> str:
    lines = []
    for group in SYN_GROUPS:
        seals = [sealer.atom(prep_for_seal(w)) for w in group]
        lines.append("SYN: " + " ~ ".join(seals))
    return "\n".join(lines)


def opaque_retrieve(
    q_sealed: str,
    ctx_sealed: str,
    k: int = TOP_K,
    q_toks: set[str] | None = None,
) -> list[dict]:
    """Rank sealed CONTEXT lines by IDF-weighted overlap with sealed QUESTION.

    Operates ONLY on seal tokens — no plaintext of CONTEXT, no gold.
    """
    lines = [ln for ln in ctx_sealed.splitlines() if ln.strip()]
    qtoks = q_toks if q_toks is not None else seal_tokens(q_sealed)
    line_toks = [seal_tokens(ln) for ln in lines]
    df: Counter[str] = Counter()
    for t in line_toks:
        df.update(t)
    scored = []
    for i, (ln, t) in enumerate(zip(lines, line_toks)):
        inter = qtoks & t
        if not inter:
            continue
        score = sum(1.0 / (1.0 + df[x]) for x in inter)
        scored.append(
            {
                "rank": 0,
                "line_idx": i,
                "score": round(score, 4),
                "overlap_n": len(inter),
                "sealed_line": ln,
            }
        )
    scored.sort(key=lambda x: (-x["score"], x["line_idx"]))
    out = scored[:k]
    for r, row in enumerate(out, 1):
        row["rank"] = r
    return out


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    feta = load_feta(6, rng)
    cases_spec = SUBJECTIVE_CASES + feta
    doc_ctx = {k: seal_text(sealer, v) for k, v in DOCS.items()}

    nl_items, ev_items, sr_items, eh_items, cases = [], [], [], [], []

    for spec in cases_spec:
        if spec["doc"] == "feta":
            ctx = seal_text(sealer, spec["context_plain"])
        else:
            ctx = doc_ctx[spec["doc"]]
        evid_sealed = [seal_text(sealer, e) for e in spec["gold_evidence_plain"]]
        q_sealed = seal_text(sealer, spec["question"])
        q_toks = expand_query_seals(sealer, q_sealed, spec["question"])
        legend = sealed_syn_legend(sealer)

        retrieved = opaque_retrieve(q_sealed, ctx, TOP_K, q_toks=q_toks)
        retrieved_block = (
            "\n".join(f"R{r['rank']}: {r['sealed_line']}" for r in retrieved)
            if retrieved
            else "(no seal-overlap lines)"
        )

        # post-hoc: did opaque retrieve hit gold? (scoring only — not shown to MUT)
        gold_hit = 0.0
        if evid_sealed:
            hits = 0
            blob = " ".join(r["sealed_line"] for r in retrieved)
            for g in evid_sealed:
                gtoks = [t for t in g.split() if SEAL_RE.fullmatch(t)]
                if gtoks and sum(1 for t in gtoks if t in blob) / len(gtoks) >= 0.6:
                    hits += 1
            gold_hit = hits / len(evid_sealed)

        cid_nl = f"{spec['id']}_NL"
        cid_ev = f"{spec['id']}_EV"
        cid_sr = f"{spec['id']}_SR"
        cid_eh = f"{spec['id']}_EH"

        nl_body = (
            "OPAQUE GENERATION control — answer lives somewhere in sealed CONTEXT.\n"
            "Do not decrypt. Find and answer in seals.\n"
            f"QUESTION:\n{q_sealed}\n\nCONTEXT:\n{ctx}\n\n"
            f"Reply:\nANSWER_SEALED[{cid_nl}]: <sealed answer>\n"
            f"or ANSWER_SEALED[{cid_nl}]: UNKNOWN"
        )

        ev_body = (
            "OPAQUE GENERATION — LLM must find supporting sealed spans (no gold).\n"
            "1) Copy 1-3 exact sealed spans from CONTEXT that support the answer.\n"
            "2) Write ANSWER_SEALED using ONLY tokens from those spans.\n"
            f"QUESTION:\n{q_sealed}\n\nCONTEXT:\n{ctx}\n\n"
            f"Reply:\nEVIDENCE_SEALED[{cid_ev}]: <span1> || <span2>\n"
            f"ANSWER_SEALED[{cid_ev}]: <sealed answer>"
        )

        sr_body = (
            "OPAQUE RETRIEVE + GENERATE (CLAIM path — no gold answer lines)\n"
            "Finder used ONLY sealed-token overlap (+ sealed synonym legend expansion).\n"
            "No plaintext CONTEXT reader. No gold spans.\n"
            "Compose ANSWER_SEALED from RETRIEVED seals only.\n"
            f"QUESTION:\n{q_sealed}\n\n"
            f"SEALED_SYN_LEGEND:\n{legend}\n\n"
            f"RETRIEVED (top-{TOP_K} sealed lines):\n{retrieved_block}\n\n"
            f"Reply:\nEVIDENCE_SEALED[{cid_sr}]: <copy R-lines joined by ||>\n"
            f"ANSWER_SEALED[{cid_sr}]: <sealed answer from retrieved tokens>"
        )

        handle_block = "\n".join(f"EVIDENCE_HANDLE: {s}" for s in evid_sealed)
        eh_body = (
            "DIAGNOSTIC ONLY — oracle gold sealed spans (NOT the opaque claim).\n"
            f"QUESTION:\n{q_sealed}\n\nHANDLES:\n{handle_block}\n\n"
            f"Reply:\nEVIDENCE_SEALED[{cid_eh}]: <handles ||>\n"
            f"ANSWER_SEALED[{cid_eh}]: <sealed answer>"
        )

        nl_items.append((cid_nl, nl_body))
        ev_items.append((cid_ev, ev_body))
        sr_items.append((cid_sr, sr_body))
        eh_items.append((cid_eh, eh_body))
        cases.append(
            {
                "id_nl": cid_nl,
                "id_ev": cid_ev,
                "id_sr": cid_sr,
                "id_eh": cid_eh,
                "doc": spec["doc"],
                "question": spec["question"],
                "gold_evidence_plain": spec["gold_evidence_plain"],
                "gold_evidence_sealed": evid_sealed,
                "rubric_must": spec["rubric_must"],
                "gold_answer_plain": spec.get("gold_answer_plain"),
                "opaque_retrieve": retrieved,
                "opaque_retrieve_gold_hit": round(gold_hit, 3),
                "note": spec.get("note"),
            }
        )

    def pack(name, header, items):
        d = RUNS / f"{name}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        lines = [
            "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
            "Same encoding on QUESTION and CONTEXT.",
            header,
            "",
        ]
        for cid, body in items:
            lines.append(f"##### ID {cid} #####\n{body}\n")
        p = d / "BATCH.txt"
        p.write_text("\n".join(lines))
        return str(p)

    paths = {
        "NL": pack("NL", "Opaque gen control: full sealed C.", nl_items),
        "EVIDENCE": pack("EVIDENCE", "LLM finds spans (no gold).", ev_items),
        "SEAL_RETRIEVE": pack(
            "SEAL_RETRIEVE",
            "Opaque seal-overlap retrieve then generate (CLAIM path).",
            sr_items,
        ),
        "EV_HANDLES": pack(
            "EV_HANDLES",
            "DIAGNOSTIC oracle only — not the opaque claim.",
            eh_items,
        ),
    }

    mean_hit = sum(c["opaque_retrieve_gold_hit"] for c in cases) / max(1, len(cases))
    harness = {
        "n": len(cases),
        "n_policy": len(SUBJECTIVE_CASES),
        "n_feta": len(feta),
        "top_k": TOP_K,
        "paths": paths,
        "cases": cases,
        "rev": sealer.rev,
        "opaque_retrieve_mean_gold_hit": round(mean_hit, 3),
        "claim": (
            "Opaque generation: find+answer under seals without gold and without "
            "a cleartext Q/C reader. SEAL_RETRIEVE = seal-token IDF overlap → generate. "
            "EV_HANDLES is diagnostic only."
        ),
    }
    (RESULTS / "subjective_harness.json").write_text(json.dumps(harness, indent=2))
    print(
        json.dumps(
            {
                "n": len(cases),
                "opaque_retrieve_mean_gold_hit": round(mean_hit, 3),
                "paths": paths,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    build()
