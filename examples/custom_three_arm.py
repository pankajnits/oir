#!/usr/bin/env python3
"""Bring-your-own graph: engine ceiling for plan arms; write two NL prompts.

JSON list of {id, question, start, rels, triples, gold}
(see examples/custom_graph.example.json). No LLM for PLAIN/SEAL plans.

  BOUND_NL  — start bound into q, entities+relations sealed, no PATH.
              Unique-path / copy-and-walk class. Not CEO SEAL_NL 0/32.
  NOBIND_NL — piecewise HMAC of the English question (spaced names split).
              This is the CEO missing-start class. Single-token starts still land.

Neither file is the paper free two-path cell (OpenAI 6/32, no PATH, English
entities, plaintext city).

    python3 examples/custom_three_arm.py examples/custom_graph.example.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from oir import MiddleLayer, SealRouter
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from oir import MiddleLayer, SealRouter


def load_items(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if not isinstance(data, list) or not data:
        raise SystemExit(f"{path}: expected a non-empty JSON list")
    return data


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/custom_graph.example.json")
    out_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("results/custom_three_arm")
    items = load_items(src)
    out_dir = out_root / src.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    plain_n = seal_n = 0
    rows = []
    for it in items:
        cid = it["id"]
        start = it["start"]
        rels = list(it["rels"])
        triples = [tuple(t) for t in it["triples"]]
        gold = it["gold"]

        plain = gold in SealRouter(triples).path(start, rels)
        layer = MiddleLayer()
        sealed = layer.seal_triples(triples)
        seal = layer.atom(gold) in SealRouter(sealed).path(
            layer.atom(start), [layer.atom(r) for r in rels]
        )
        plain_n += int(plain)
        seal_n += int(seal)

        ctx = "\n".join(
            ["| src | rel | dst |", "| --- | --- | --- |"]
            + [f"| {h} | {r} | {t} |" for h, r, t in sealed]
        )
        bound_q, start_s, _ = layer.seal_question_bound(it["question"], [start])
        nobind_q = layer.nobind_question(it["question"])
        bound_prompt = layer.pack_prompt(cid, bound_q, "", ctx)
        nobind_prompt = layer.pack_prompt(cid, nobind_q, "", ctx)
        (out_dir / f"{cid}_BOUND_NL.txt").write_text(bound_prompt)
        (out_dir / f"{cid}_NOBIND_NL.txt").write_text(nobind_prompt)
        leaked = layer.call(
            cid=cid,
            app_question=it["question"],
            names=[start],
            triples=triples,
            extra_leak_names=[gold],
        ).leaked
        rows.append(
            {
                "id": cid,
                "plain_ok": plain,
                "seal_prog_ok": seal,
                "gold": gold,
                "leaked": leaked,
                "start_in_bound_q": start_s in bound_q,
                "start_in_nobind_q": start_s in nobind_q,
            }
        )

    n = len(items)
    summary = {
        "n": n,
        "PLAIN_PROG_engine": f"{plain_n}/{n}",
        "SEAL_PROG_engine": f"{seal_n}/{n}",
        "BOUND_NL_prompts": str(out_dir),
        "NOBIND_NL_prompts": str(out_dir),
        "note": (
            "BOUND_NL binds start into q (not CEO SEAL_NL). "
            "NOBIND_NL is piecewise HMAC; spaced starts miss V(G). "
            "Neither is the free two-path 6/32 cell."
        ),
        "rows": rows,
    }
    out_json = out_dir / "engine_ceiling.json"
    out_json.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2))
    print("wrote", out_json)


if __name__ == "__main__":
    main()
