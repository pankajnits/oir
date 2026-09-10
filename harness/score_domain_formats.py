#!/usr/bin/env python3
"""Score domain_formats from results/domain_replies_<model>/."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
H = json.loads((RESULTS / "domain_formats_harness.json").read_text())
PLAIN = re.compile(r"ANSWER_PLAIN\[([^\]]+)\]:\s*(\S+)", re.I)
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)

ARMS = [
    ("TABLE_PLAIN_PROG", "plain"),
    ("TABLE_SEAL_PROG", "seal"),
    ("TABLE_SEAL_NL", "seal"),
    ("TABLE_SEAL_BOTH", "seal"),
    ("JSON_PLAIN_PROG", "plain"),
    ("JSON_SEAL_PROG", "seal"),
    ("JSON_SEAL_NL", "seal"),
    ("JSON_SEAL_BOTH", "seal"),
    ("VAULT_MILD", "seal"),
    ("VAULT_STRICT_PROG", "seal"),
    ("VAULT_STRICT_NL", "seal"),
    ("VAULT_STRICT_BOTH", "seal"),
]


def parse(path: Path, kind: str) -> dict[str, str]:
    if not path.exists():
        return {}
    rx = PLAIN if kind == "plain" else SEAL
    return {m.group(1): m.group(2) for m in rx.finditer(path.read_text())}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "auto"
    reply = RESULTS / f"domain_replies_{model}"
    cases = H["cases"]
    n = len(cases)
    summary, rows = {}, []
    for arm, kind in ARMS:
        preds = parse(reply / f"{arm}.txt", kind)
        oks = []
        for c in cases:
            if kind == "plain":
                cid = {
                    "TABLE_PLAIN_PROG": f"DOM_TABLE_PLAIN_{c['i']}",
                    "JSON_PLAIN_PROG": f"DOM_JSON_PLAIN_{c['i']}",
                }[arm]
                gold = c["expect_plain"]
            else:
                cid_map = {
                    "TABLE_SEAL_PROG": f"DOM_TABLE_SEALPROG_{c['i']}",
                    "TABLE_SEAL_NL": f"DOM_TABLE_SEALNL_{c['i']}",
                    "TABLE_SEAL_BOTH": f"DOM_TABLE_SEALBOTH_{c['i']}",
                    "JSON_SEAL_PROG": f"DOM_JSON_SEALPROG_{c['i']}",
                    "JSON_SEAL_NL": f"DOM_JSON_SEALNL_{c['i']}",
                    "JSON_SEAL_BOTH": f"DOM_JSON_SEALBOTH_{c['i']}",
                    "VAULT_MILD": f"DOM_VAULT_MILD_{c['i']}",
                    "VAULT_STRICT_PROG": f"DOM_VAULT_STRICTPROG_{c['i']}",
                    "VAULT_STRICT_NL": f"DOM_VAULT_STRICTNL_{c['i']}",
                    "VAULT_STRICT_BOTH": f"DOM_VAULT_STRICTBOTH_{c['i']}",
                }
                cid = cid_map[arm]
                gold = c["expect_seal"]
            pred = preds.get(cid, "MISSING")
            ok = pred == gold
            oks.append(ok)
            rows.append({"arm": arm, "id": cid, "gold": gold, "pred": pred, "ok": ok})
        summary[arm] = {
            "score": f"{sum(oks)}/{n}",
            "missing": sum(1 for r in rows[-n:] if r["pred"] == "MISSING"),
        }
    out = {
        "model": model,
        "n": n,
        "summary": summary,
        "rows": rows,
        "reply_dir": str(reply),
        "verdict": (
            "SUPPORTED format transfer"
            if all(
                summary[a]["score"].startswith("12/") or summary[a]["score"].startswith("11/")
                for a in ("TABLE_PLAIN_PROG", "TABLE_SEAL_PROG", "JSON_PLAIN_PROG", "JSON_SEAL_PROG")
            )
            and all(summary[a]["score"].startswith("0/") for a in ("TABLE_SEAL_NL", "JSON_SEAL_NL"))
            and all(
                summary[a]["score"].startswith("12/") or summary[a]["score"].startswith("11/")
                for a in ("TABLE_SEAL_BOTH", "JSON_SEAL_BOTH", "VAULT_STRICT_BOTH")
            )
            else "MIXED — see summary"
        ),
    }
    path = RESULTS / f"domain_formats_{model}.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(out["verdict"])
    print("wrote", path)


if __name__ == "__main__":
    main()
