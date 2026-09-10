#!/usr/bin/env python3
"""Future-domain unlock suite: LEGAL / CODE / CLOUD / CLINIC.

Complex payload (tables + JSON + notes). Competing subjective advice:
gold recommended_action is in the start-ID note; a distractor note has a
different action (trap). Extractive copy vs free sealed NL.

Not HIPAA/legal advice; synthetic IDs. Not G-Rev1.
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
RUNS = ROOT / "runs" / "future_unlock"
KEY = b"oir-future-unlock-v1"
SEED = 20260813
N = 8


def pack(kind, header, items):
    tag = {"plain": "ANSWER_PLAIN", "seal": "ANSWER_SEALED"}[kind]
    lines = [
        "MODEL UNDER TEST. Read ONLY this file. No decrypt. No world knowledge.",
        f"Format: {tag}[<id>]: <token_or_UNKNOWN>",
        "Answer EVERY ID. If two actions appear, use the note that names the queried ID.",
        "",
        header,
        "",
    ]
    for cid, body in items:
        lines.append(f"##### ID {cid} #####\n{body}\n")
    return "\n".join(lines)


def worlds(i):
    sid = f"ID{i}"
    # four rotating domains
    kind = ["LEGAL", "CODE", "CLOUD", "CLINIC"][i % 4]
    if kind == "LEGAL":
        start, r1, r2, r3 = f"Docket_{i}", "filed_as", "before_judge", "sits_in"
        mid1, mid2, end = f"Matter_{i}", f"Judge_{i}", f"Venue_{i}"
        gold_a, trap_a = "file_motion_to_compel", "settle_without_prejudice"
        qh = f"Which venue sits the judge on docket {start}?"
        qs = f"What should counsel do next for {start}? Return recommended_action only."
        note_g = f"{start} discovery overdue. Recommended_action {gold_a}. Do not {trap_a}."
        note_t = f"{start}_X is a nuisance claim. Recommended_action {trap_a}."
    elif kind == "CODE":
        start, r1, r2, r3 = f"sha_{i}abc", "touches", "owned_by", "pages"
        mid1, mid2, end = f"svc_{i}", f"eng_{i}", f"region_{i}"
        gold_a, trap_a = "hold_release", "ship_now"
        qh = f"Which region does the owner of commit {start} page?"
        qs = f"Ship decision for {start}? Return recommended_action only."
        note_g = f"Commit {start} changes authz. Recommended_action {gold_a}. Tests red."
        note_t = f"{start}_X is a docs typo. Recommended_action {trap_a}."
    elif kind == "CLOUD":
        start, r1, r2, r3 = f"arn_{i}", "in_account", "owned_by", "in_zone"
        mid1, mid2, end = f"acct_{i}", f"owner_{i}", f"zone_{i}"
        gold_a, trap_a = "rotate_keys", "ignore_finding"
        qh = f"Which zone is the owner of {start} in?"
        qs = f"Remediation for {start}? Return recommended_action only."
        note_g = f"Resource {start} public bucket. Recommended_action {gold_a}."
        note_t = f"{start}_X is retired. Recommended_action {trap_a}."
    else:
        start, r1, r2, r3 = f"pat_{i}", "had_enc", "seen_by", "clinic_in"
        mid1, mid2, end = f"enc_{i}", f"md_{i}", f"clinic_{i}"
        gold_a, trap_a = "repeat_labs_48h", "discharge_home"
        qh = f"Which clinic saw the clinician for patient {start}?"
        qs = f"Next clinical step for {start}? Return recommended_action only. Not medical advice."
        note_g = f"Patient {start} rising creatinine. Recommended_action {gold_a}."
        note_t = f"{start}_X is well. Recommended_action {trap_a}."
    edges = [
        (start, r1, mid1),
        (mid1, r2, mid2),
        (mid2, r3, end),
        (f"{start}_X", r1, f"{mid1}_X"),
        (f"{mid1}_X", r2, f"{mid2}_X"),
        (f"{mid2}_X", r3, f"{end}_X"),
    ]
    notes = note_g + " " + note_t
    return {
        "kind": kind,
        "start": start,
        "rels": [r1, r2, r3],
        "end": end,
        "edges": edges,
        "gold_a": gold_a,
        "trap_a": trap_a,
        "qh": qh,
        "qs": qs,
        "notes": notes,
        "sid": sid,
    }


def render(w, sealer=None):
    def t(x):
        return str(x) if sealer is None else sealer.atom(x)

    hops = [(t(h), t(r), t(tl)) for h, r, tl in w["edges"]]
    ctx = SealRouter(hops).render() if sealer else SealRouter(w["edges"]).render()
    notes = w["notes"]
    if sealer:
        for a in sorted({w["start"], w["end"], w["gold_a"], w["trap_a"], *[x for e in w["edges"] for x in e]}, key=len, reverse=True):
            notes = notes.replace(a, sealer.atom(a))
    return ctx + "\n\nNOTES:\n" + notes


def build():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    arms = ("HOP_PLAIN", "HOP_SEAL_PROG", "HOP_SEAL_NL", "SUBJ_NL", "SUBJ_EXTRACT")
    buckets = {a: [] for a in arms}
    cases = []
    for i in range(N):
        w = worlds(i)
        rng.shuffle(w["edges"])
        gold_h_s = sealer.atom(w["end"])
        gold_a_s = sealer.atom(w["gold_a"])
        trap_s = sealer.atom(w["trap_a"])
        plain = render(w, None)
        sealed = render(w, sealer)
        start_s = sealer.atom(w["start"])
        prog = f"PATH_QUERY\nSTART {start_s}\nR1 {sealer.atom(w['rels'][0])}\nR2 {sealer.atom(w['rels'][1])}\nR3 {sealer.atom(w['rels'][2])}\nExecute path; return final tail."
        ids = {a: f"FU_{a}_{i}" for a in arms}
        buckets["HOP_PLAIN"].append((ids["HOP_PLAIN"], f"QUESTION:\n{w['qh']}\n\nCONTEXT:\n{plain}"))
        buckets["HOP_SEAL_PROG"].append((ids["HOP_SEAL_PROG"], f"{prog}\n\nCONTEXT:\n{sealed}"))
        buckets["HOP_SEAL_NL"].append((ids["HOP_SEAL_NL"], f"QUESTION:\n{sealer.text(w['qh'])}\n\nCONTEXT:\n{sealed}"))
        buckets["SUBJ_NL"].append((ids["SUBJ_NL"], f"QUESTION:\n{sealer.text(w['qs'])}\n\nCONTEXT:\n{sealed}"))
        buckets["SUBJ_EXTRACT"].append(
            (
                ids["SUBJ_EXTRACT"],
                "EXTRACTIVE: copy the recommended_action token from the NOTES line that contains the queried start ID. Do not invent.\n"
                f"START {start_s}\nQUESTION:\n{sealer.text(w['qs'])}\n\nCONTEXT:\n{sealed}",
            )
        )
        cases.append(
            {
                "i": i,
                "kind": w["kind"],
                "ids": ids,
                "expect_hop_plain": w["end"],
                "expect_hop_seal": gold_h_s,
                "expect_subj": gold_a_s,
                "trap_subj": trap_s,
                "qh": w["qh"],
                "qs": w["qs"],
                "start_in_nl_q": start_s in sealer.text(w["qh"]),
            }
        )
    RUNS.mkdir(parents=True, exist_ok=True)
    headers = {
        "HOP_PLAIN": "3-hop English Q + plaintext graph/notes.",
        "HOP_SEAL_PROG": "Gold PATH over sealed graph (ceiling).",
        "HOP_SEAL_NL": "Sealed NL 3-hop. Start ID may still be in Q (copy-and-walk caveat).",
        "SUBJ_NL": "Sealed subjective: recommended_action. Competing trap action in another note.",
        "SUBJ_EXTRACT": "Extractive copy of recommended_action for the queried start ID.",
    }
    kinds = {
        "HOP_PLAIN": "plain",
        "HOP_SEAL_PROG": "seal",
        "HOP_SEAL_NL": "seal",
        "SUBJ_NL": "seal",
        "SUBJ_EXTRACT": "seal",
    }
    paths = {}
    for arm in arms:
        d = RUNS / f"{arm}_ONLY"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "BATCH.txt"
        p.write_text(pack(kinds[arm], headers[arm], buckets[arm]))
        paths[arm] = str(p)
    out = RESULTS / "future_unlock_harness.json"
    out.write_text(
        json.dumps(
            {
                "n": N,
                "suite": "future_unlock",
                "paths": paths,
                "cases": cases,
                "nonclaim": "Synthetic LEGAL/CODE/CLOUD/CLINIC. Not legal/medical advice. Not G-Rev1. Extractive ≠ authoring.",
            },
            indent=2,
        )
    )
    print(json.dumps({"n": N, "kinds": sorted({c['kind'] for c in cases}), "out": str(out)}, indent=2))


if __name__ == "__main__":
    build()
