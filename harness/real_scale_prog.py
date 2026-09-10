#!/usr/bin/env python3
"""Scaled real-data same-encoding path-program (the fix that worked)."""
from __future__ import annotations
import hashlib, hmac, json, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data/real/wikidata_ceo_hops_v2.json").read_text())
RESULTS = ROOT / "results"
KEY = b"oir-real-scale-v2"
SEED = 42

class EntitySeal:
    def __init__(self, key: bytes):
        self.key = key
        self.fwd = {}
        self.rev = {}
    def atom(self, a: str) -> str:
        if a not in self.fwd:
            d = hmac.new(self.key, a.encode(), hashlib.sha256).digest()
            t = "E" + d[:6].hex()
            self.fwd[a] = t
            self.rev[t] = a
        return self.fwd[a]

def render(sealer, edges):
    return "\n".join(f"{sealer.atom(h)} | {sealer.atom(r)} | {sealer.atom(t)}" for h,r,t in edges)

def graph(row, pool, rng):
    person, company, hq = row["person"], row["company"], row["hq"]
    others = [r for r in pool if r["company"] != company]
    decoy = rng.choice(others)
    hold, part = f"Hold_{company}", f"Part_{company}"
    edges = [
        (person, "works_at", company),
        (company, "headquartered_in", hq),
        (decoy["company"], "headquartered_in", decoy["hq"]),
        (company, "owned_by", hold),
        (hold, "meta_of", f"Meta_{company}"),
        (company, "partner_of", part),
        (part, "meta_of", f"PMeta_{company}"),
        (f"Decoy_{company}", "works_at", decoy["company"]),
    ]
    return edges, person, hq

def main():
    rng = random.Random(SEED)
    sealer = EntitySeal(KEY)
    for r in ("works_at","headquartered_in","owned_by","partner_of","meta_of"):
        sealer.atom(r)
    pool = DATA[:60]
    quiz = pool[:24]
    cases=[]; lines=[
        "MODEL UNDER TEST. No tools. Read ONLY this file.\n",
        "Same encoding. PATH_QUERY: START -R1-> x -R2-> y. Return y.\n",
        "No external knowledge. Format: ANSWER_SEALED[<id>]: <seal_or_UNKNOWN>\n",
    ]
    for i,row in enumerate(quiz):
        edges, person, hq = graph(row, pool, rng)
        cid=f"SCALE_PROG_{i}"
        body=(
            f"PATH_QUERY\nSTART {sealer.atom(person)}\n"
            f"R1 {sealer.atom('works_at')}\nR2 {sealer.atom('headquartered_in')}\n"
            f"Return y seal only.\n\nCONTEXT:\n{render(sealer, edges)}"
        )
        lines.append(f"\n##### ID {cid} #####\n{body}\n")
        cases.append({"id":cid,"expect":sealer.atom(hq),"plain":hq,"person":person,"company":row["company"]})
    d=ROOT/"runs"/"real_scale_prog_ONLY"
    d.mkdir(parents=True, exist_ok=True)
    (d/"BATCH_scale_prog.txt").write_text("\n".join(lines))
    (RESULTS/"real_scale_prog_harness.json").write_text(json.dumps({"n":len(cases),"cases":cases,"rev":sealer.rev},indent=2))
    print(json.dumps({"n":len(cases)},indent=2))

if __name__=="__main__":
    main()
