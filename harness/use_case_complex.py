#!/usr/bin/env python3
"""
Complex data / complex questions / subjective / extra use cases.

Worlds (cycled): HR, TICKET, ONCALL — each a 3-hop join plus distractors.
Question types:
  3HOP   — person/ticket/service → … → city/region
  COUNT  — how many entities share the gold city (integer)
  SUBJ   — recommended action buried in notes; NL vs LOOKUP program

Arms: PLAIN_PROG, SEAL_PROG, SEAL_NL, SEAL_BOTH (3HOP);
      COUNT_PROG, COUNT_NL;
      SUBJ_NL, SUBJ_PROG.
Seal / ask / check are explicit in the harness JSON.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "use_case_complex"
KEY = b"oir-use-case-complex-v1"
SEED = 20260813
N = 8


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def pack(kind: str, header: str, items: list[tuple[str, str]]) -> str:
    fmt = {
        "plain": "ANSWER_PLAIN[<id>]: <token_or_UNKNOWN>",
        "seal": "ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>",
        "num": "ANSWER_NUM[<id>]: <integer_or_UNKNOWN>",
    }[kind]
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
        f"Format: {fmt}",
        "Answer EVERY ID.",
        "",
        header,
        "",
    ]
    for cid, body in items:
        lines.append(f"##### ID {cid} #####\n{body}\n")
    return "\n".join(lines)


def world_hr(rng, recs, i):
    people = recs[i : i + 5]
    depts = [f"Dept_{i}_{k}" for k in range(3)]
    sites = [f"Site_{i}_{k}" for k in range(3)]
    cities = [p["hq"] for p in people[:3]]
    emp = people[0]["person"]
    dept, site, city = depts[0], sites[0], cities[0]
    edges = [(emp, "in_dept", dept), (dept, "at_site", site), (site, "in_city", city)]
    # distractors
    for k, p in enumerate(people[1:4], 1):
        edges += [
            (p["person"], "in_dept", depts[k % 3]),
            (depts[k % 3], "at_site", sites[k % 3]),
            (sites[k % 3], "in_city", cities[k % 3] if k % 3 < len(cities) else cities[0]),
        ]
    notes = (
        f"{emp} access review: if badge_fail occurs twice, freeze_badge and page_site_security. "
        f"Do not email the password. Recommended_action freeze_badge."
    )
    action = "freeze_badge"
    return {
        "use": "HR",
        "start": emp,
        "rels": ["in_dept", "at_site", "in_city"],
        "end": city,
        "edges": edges,
        "count_city": city,
        "notes": notes,
        "action": action,
        "q3": f"Which city is the site of the department of {emp.replace('_', ' ')} in?",
        "qc": f"How many sites are in_city {city} in this snapshot?",
        "qs": f"What is the recommended_action if badge_fail occurs twice for {emp.replace('_', ' ')}?",
        "tables_plain": None,  # filled below
    }


def world_ticket(rng, recs, i):
    people = recs[i : i + 5]
    cust = people[0]["person"]
    acct = f"Acct_{i}"
    region = people[0]["hq"]
    tid = f"TCK_{i}"
    edges = [
        (tid, "opened_by", cust),
        (cust, "billed_to", acct),
        (acct, "in_region", region),
    ]
    for k, p in enumerate(people[1:4], 1):
        tk, ac = f"TCK_{i}_{k}", f"Acct_{i}_{k}"
        edges += [
            (tk, "opened_by", p["person"]),
            (p["person"], "billed_to", ac),
            (ac, "in_region", p["hq"]),
        ]
    notes = (
        f"Ticket {tid}: customer reports billing_outage. If severity is sev1, "
        f"page_oncall and open_war_room. Recommended_action page_oncall."
    )
    return {
        "use": "TICKET",
        "start": tid,
        "rels": ["opened_by", "billed_to", "in_region"],
        "end": region,
        "edges": edges,
        "count_city": region,
        "notes": notes,
        "action": "page_oncall",
        "q3": f"Which region is ticket {tid} billed into?",
        "qc": f"How many accounts are in_region {region} in this snapshot?",
        "qs": f"What is the recommended_action for sev1 on ticket {tid}?",
    }


def world_oncall(rng, recs, i):
    people = recs[i : i + 5]
    svc = f"svc_{people[0]['company']}"
    owner = people[0]["person"]
    team = f"Team_{i}"
    city = people[0]["hq"]
    edges = [
        (svc, "owned_by", owner),
        (owner, "on_team", team),
        (team, "based_in", city),
    ]
    for k, p in enumerate(people[1:4], 1):
        s, t = f"svc_{p['company']}", f"Team_{i}_{k}"
        edges += [
            (s, "owned_by", p["person"]),
            (p["person"], "on_team", t),
            (t, "based_in", p["hq"]),
        ]
    notes = (
        f"Service {svc} paging. If error_budget_burn exceeds 2 percent, "
        f"declare_incident and page_secondary. Recommended_action declare_incident."
    )
    return {
        "use": "ONCALL",
        "start": svc,
        "rels": ["owned_by", "on_team", "based_in"],
        "end": city,
        "edges": edges,
        "count_city": city,
        "notes": notes,
        "action": "declare_incident",
        "q3": f"Where is the on-call team for service {svc} based?",
        "qc": f"How many teams are based_in {city} in this snapshot?",
        "qs": f"What is the recommended_action if error_budget_burn exceeds 2 percent for {svc}?",
    }


def render_complex(w, sealer=None, mild_keys=False):
    """Tables + nested JSON + notes (complex payload)."""

    def t(x):
        if sealer is None:
            return str(x)
        if mild_keys and x in w["rels"] + ["recommended_action"]:
            return x
        return sealer.atom(x)

    rels = w["rels"]
    # group edges into 3 tables
    t1, t2, t3 = [], [], []
    for h, r, tail in w["edges"]:
        if r == rels[0]:
            t1.append([t(h), t(tail)])
        elif r == rels[1]:
            t2.append([t(h), t(tail)])
        else:
            t3.append([t(h), t(tail)])
    h1 = [t("src"), t(rels[0])]
    h2 = [t("mid"), t(rels[1])]
    h3 = [t("tail"), t(rels[2])]
    tables = (
        f"TABLE hop1\n{md_table(h1, t1)}\n\nTABLE hop2\n{md_table(h2, t2)}\n\n"
        f"TABLE hop3\n{md_table(h3, t3)}"
    )
    js = {
        "use_case": t(w["use"]),
        "graph": {
            t(h): {t(r) if not mild_keys else r: t(tail)} for h, r, tail in w["edges"]
        },
        "notes": sealer.text(w["notes"]) if sealer else w["notes"],
    }
    return tables + "\n\nJSON\n" + json.dumps(js, indent=2)


def count_rel_obj(edges, rel, obj) -> int:
    return sum(1 for h, r, t in edges if r == rel and t == obj)


def build():
    graph = json.loads((ROOT / "data/real/wikidata_ceo_hops_v2.json").read_text())
    rng = random.Random(SEED)
    recs = graph[:]
    rng.shuffle(recs)
    sealer = EntitySeal(KEY)
    makers = [world_hr, world_ticket, world_oncall]

    buckets = {k: [] for k in [
        "CX3_PLAIN_PROG", "CX3_SEAL_PROG", "CX3_SEAL_NL", "CX3_SEAL_BOTH",
        "COUNT_PROG", "COUNT_NL", "SUBJ_NL", "SUBJ_PROG",
    ]}
    cases = []

    for i in range(N):
        w = makers[i % 3](rng, recs, i * 5)
        rels = w["rels"]
        gold_city = w["end"]
        sealed_edges = [sealer.triple(*e) for e in w["edges"]]
        gold_seal = sealer.atom(gold_city)
        outs = SealRouter(sealed_edges).path(sealer.atom(w["start"]), [sealer.atom(r) for r in rels])
        assert list(dict.fromkeys(outs)) == [gold_seal], (w["use"], outs, gold_city)

        n_plain = count_rel_obj(w["edges"], rels[2], gold_city)
        n_seal_check = sum(
            1 for h, r, t in sealed_edges if r == sealer.atom(rels[2]) and t == gold_seal
        )
        assert n_plain == n_seal_check >= 1

        action_seal = sealer.atom(w["action"])
        ctx_plain = render_complex(w, sealer=None)
        ctx_seal = render_complex(w, sealer=sealer)
        q3s = sealer.text(w["q3"])
        qcs = sealer.text(w["qc"])
        qss = sealer.text(w["qs"])

        prog_p = (
            f"PATH_QUERY\nSTART {w['start']}\nR1 {rels[0]}\nR2 {rels[1]}\nR3 {rels[2]}\n"
            "Execute 3-hop; return final tail."
        )
        prog_s = (
            f"PATH_QUERY\nSTART {sealer.atom(w['start'])}\n"
            f"R1 {sealer.atom(rels[0])}\nR2 {sealer.atom(rels[1])}\nR3 {sealer.atom(rels[2])}\n"
            "Execute 3-hop; return final tail."
        )
        count_p = (
            f"COUNT_QUERY\nREL {rels[2]}\nOBJ {gold_city}\n"
            "Count rows whose hop3 tail equals OBJ."
        )
        count_s = (
            f"COUNT_QUERY\nREL {sealer.atom(rels[2])}\nOBJ {gold_seal}\n"
            "Count rows whose hop3 tail equals OBJ. Return an integer."
        )
        subj_p = (
            f"LOOKUP_QUERY\nFIELD recommended_action\n"
            f"Return the recommended_action token from NOTES for this incident."
        )
        # LOOKUP still needs the plaintext cue in PROG for mild; strict seals the field name in body
        subj_s = (
            f"LOOKUP_QUERY\nFIELD {sealer.atom('recommended_action')}\n"
            f"NOTES contain the action token. Return that sealed action token only."
        )

        buckets["CX3_PLAIN_PROG"].append((f"CX3_PLAIN_{i}", f"USE {w['use']}\n{prog_p}\n\nCONTEXT:\n{ctx_plain}"))
        buckets["CX3_SEAL_PROG"].append((f"CX3_SEALPROG_{i}", f"USE {sealer.atom(w['use'])}\n{prog_s}\n\nCONTEXT:\n{ctx_seal}"))
        buckets["CX3_SEAL_NL"].append((f"CX3_SEALNL_{i}", f"QUESTION:\n{q3s}\n\nCONTEXT:\n{ctx_seal}"))
        buckets["CX3_SEAL_BOTH"].append(
            (f"CX3_SEALBOTH_{i}", f"{prog_s}\n\nQUESTION:\n{q3s}\n\nCONTEXT:\n{ctx_seal}")
        )
        buckets["COUNT_PROG"].append((f"CXCOUNT_PROG_{i}", f"{count_s}\n\nCONTEXT:\n{ctx_seal}"))
        buckets["COUNT_NL"].append((f"CXCOUNT_NL_{i}", f"QUESTION:\n{qcs}\n\nCONTEXT:\n{ctx_seal}"))
        buckets["SUBJ_PROG"].append((f"CXSUBJ_PROG_{i}", f"{subj_s}\n\nCONTEXT:\n{ctx_seal}"))
        buckets["SUBJ_NL"].append((f"CXSUBJ_NL_{i}", f"QUESTION:\n{qss}\n\nCONTEXT:\n{ctx_seal}"))

        cases.append(
            {
                "i": i,
                "use": w["use"],
                "start": w["start"],
                "end": gold_city,
                "expect_plain": gold_city,
                "expect_seal": gold_seal,
                "expect_count": n_plain,
                "expect_action": w["action"],
                "expect_action_seal": action_seal,
            }
        )

    RUNS.mkdir(parents=True, exist_ok=True)
    headers = {
        "CX3_PLAIN_PROG": "3-hop PATH over readable tables+JSON (HR/TICKET/ONCALL).",
        "CX3_SEAL_PROG": "3-hop PATH over sealed tables+JSON.",
        "CX3_SEAL_NL": "Sealed 3-hop NL; no PATH.",
        "CX3_SEAL_BOTH": "Sealed 3-hop NL + PATH. Execute PATH.",
        "COUNT_PROG": "COUNT over sealed hop3 tails. ANSWER_NUM.",
        "COUNT_NL": "Sealed COUNT question; no program. ANSWER_NUM.",
        "SUBJ_PROG": "LOOKUP recommended_action in sealed notes.",
        "SUBJ_NL": "Sealed subjective NL; no LOOKUP.",
    }
    kind = {
        "CX3_PLAIN_PROG": "plain",
        "CX3_SEAL_PROG": "seal",
        "CX3_SEAL_NL": "seal",
        "CX3_SEAL_BOTH": "seal",
        "COUNT_PROG": "num",
        "COUNT_NL": "num",
        "SUBJ_PROG": "seal",
        "SUBJ_NL": "seal",
    }
    paths = {}
    for arm, items in buckets.items():
        d = RUNS / f"{arm}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack(kind[arm], headers[arm], items))
        paths[arm] = str(p)

    harness = {
        "n": N,
        "seed": SEED,
        "suite": "use_case_complex",
        "paths": paths,
        "cases": cases,
        "what": {
            "data": "3 tables + nested JSON + notes; 3-hop HR/TICKET/ONCALL",
            "complex_q": "3-hop path and COUNT of shared city/region",
            "subjective": "recommended_action in incident notes",
            "check_3hop": "exact city/region (plain) or HMAC seal",
            "check_count": "integer",
            "check_subj": "HMAC seal of action token",
        },
    }
    out = RESULTS / "use_case_complex_harness.json"
    out.write_text(json.dumps(harness, indent=2))
    print(json.dumps({"n": N, "arms": list(paths), "uses": [c["use"] for c in cases]}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    build()
