#!/usr/bin/env python3
from __future__ import annotations
import json, re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPLIES = RESULTS / "hop_ladder_replies"
HARNESS = RESULTS / "hop_ladder_harness.json"
ANS_RE = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)

def load(path):
    return {m.group(1): m.group(2) for m in ANS_RE.finditer(path.read_text())} if path.exists() else {}

def main():
    h = json.loads(HARNESS.read_text())
    prog = load(REPLIES / "SEAL_PROG_composer.txt")
    nl = load(REPLIES / "SEAL_NL_composer.txt")
    by = defaultdict(lambda: {"PROG": [], "NL": []})
    rows = []
    for c in h["cases"]:
        pp, np_ = prog.get(c["prog_id"], ""), nl.get(c["nl_id"], "")
        pok, nok = pp == c["gold"], np_ == c["gold"]
        by[c["hop"]]["PROG"].append(pok)
        by[c["hop"]]["NL"].append(nok)
        rows.append({**c, "pred_prog": pp, "pred_nl": np_, "prog_ok": pok, "nl_ok": nok})
    summary = {
        hop: {
            "PROG": f"{sum(v['PROG'])}/{len(v['PROG'])}",
            "NL": f"{sum(v['NL'])}/{len(v['NL'])}",
        }
        for hop, v in sorted(by.items())
    }
    out = {"summary": summary, "rows": rows,
           "verdict": "SUPPORTED if PROG high across hops and NL near 0"}
    (RESULTS / "hop_ladder_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
