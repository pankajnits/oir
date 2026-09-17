#!/usr/bin/env python3
"""Clone-and-run demo of the paper's Findings spine (H1–H4, OA, H6–H8 + controls).

No network. Does not rewrite ``runs/``. Does not re-score n=32.

For each locked cell this script:
  1. Reconstructs item 0 with the same harness constructors, or inspects the
     locked isolation prompt.
  2. Runs SealRouter / hop counts (engine facts the LLM is *not*).
  3. Prints the locked OpenAI score from ``results/*.json``.

Product PATH/JOIN (names stay in the app) is ``examples/middleware_hr.py``.
That is the H2 execution control, not the free two-path cell.

    python3 examples/paper_spine.py
    OPENAI_API_KEY=... python3 examples/paper_spine.py --openai
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter  # noqa: E402
from oir.adapters import load_json_records  # noqa: E402

HMAC = re.compile(r"^E[0-9a-f]{12}$", re.I)
DEMO_ANS = re.compile(r"^ANSWER_SEALED:\s*(\S+)\s*$", re.I | re.M)
LEAK_VERBS = ("directed", "starred", "written", "writer", "director")
FAM_2X2 = (("gpt56", "OpenAI"), ("composer25", "composer"), ("grok45", "Grok"))
FAM_DP = (("gpt56", "OpenAI"), ("composer25ff", "composer"), ("grok45ff", "Grok"))
FAM_ER = (("gpt56", "OpenAI"), ("composer25", "composer"), ("grok45", "Grok"))


def load_mod(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "harness" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def locked(path: Path) -> dict:
    return json.loads(path.read_text())


def score(blob: dict, arm: str) -> str:
    return blob["summary"][arm]["score"]


def prompt(suite: str, arm: str, i: int = 0) -> str:
    p = ROOT / "runs" / suite / arm / f"item_{i}" / "prompt.txt"
    if not p.is_file():
        raise FileNotFoundError(p)
    return p.read_text()


def last_demo_answer(text: str) -> str:
    ms = list(DEMO_ANS.finditer(text.split("--- QUIZ ---")[0]))
    return ms[-1].group(1) if ms else ""


def q_block(text: str) -> str:
    after = text.split("QUESTION", 1)[-1]
    return after.split("CONTEXT:", 1)[0]


def fam_locked(stem: str, arm: str, tags: tuple[tuple[str, str], ...]) -> str:
    parts = []
    for tag, label in tags:
        p = ROOT / "results" / f"{stem}_{tag}.json"
        if p.is_file():
            parts.append(f"{label} {score(locked(p), arm)}")
    return "; ".join(parts)


def rel_atoms(blob: str) -> set[str]:
    out: set[str] = set()
    for line in blob.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) == 3 and HMAC.match(cells[1]):
            out.add(cells[1])
    return out



@dataclass
class Cell:
    hid: str
    title: str
    engine: str
    locked_score: str
    note: str
    ok: bool = True
    extra: dict = field(default_factory=dict)


def _picked_ceo(fact):
    recs = load_json_records(fact.SOURCE)
    rng = random.Random(fact.SEED)
    pool = [r for r in recs if r["hq"] and r["person"] and r["company"]]
    picked = rng.sample(pool, fact.N)
    row = picked[0]
    decoy = picked[1]
    if decoy["hq"] == row["hq"] or decoy["person"] == row["person"]:
        decoy = {"person": "DecoyPerson_0", "company": "DecoyCo_0", "hq": "DecoyCity_0"}
    return row, decoy


def cells_2x2(fact) -> list[Cell]:
    row, decoy = _picked_ceo(fact)
    u, a = fact.unique_edges(row, decoy), fact.ambig_edges(row, decoy)
    u_hops, a_hops = fact.two_hops(u, row["person"]), fact.two_hops(a, row["person"])
    gold_rels = ["works_at", "headquartered_in"]
    sealer = EntitySeal(fact.item_key(0))
    gold_s = [sealer.atom(r) for r in gold_rels]
    u_seal = [(h, sealer.atom(r), t) for h, r, t in u]
    a_seal = [(h, sealer.atom(r), t) for h, r, t in a]
    plan_u = SealRouter(u_seal).path(row["person"], gold_s)
    plan_a = SealRouter(a_seal).path(row["person"], gold_s)
    u_tails = [t for *_, t in u_hops]
    a_tails = [t for *_, t in a_hops]
    pu = prompt("factorial_2x2_iso", "OPAQUE_UNIQUE")
    pa = prompt("factorial_2x2_iso", "OPAQUE_AMBIG")
    pp = prompt("factorial_2x2_iso", "OPAQUE_AMBIG_PLAN")
    js = locked(ROOT / "results/factorial_2x2_iso_gpt56.json")
    amb = js["summary"]["OPAQUE_AMBIG"]
    start_in = row["person"] in pu and row["person"] in pa
    no_path_free = "PATH_QUERY" not in pu and "PATH_QUERY" not in pa
    plan_has_path = "PATH_QUERY" in pp or "START " in pp
    ok = (
        len(u_hops) == 1
        and len(a_hops) == 2
        and u_tails == [row["hq"]]
        and row["hq"] in a_tails
        and plan_u == [row["hq"]]
        and plan_a == [row["hq"]]
        and start_in
        and no_path_free
        and plan_has_path
        and score(js, "OPAQUE_UNIQUE") == "32/32"
        and score(js, "OPAQUE_AMBIG") == "6/32"
        and amb["unknown"] == 24
        and amb["decoy"] == 2
    )
    return [
        Cell(
            "H1",
            "Opacity alone blocks traversal? Unique opaque, start in q, no plan",
            f"1 hop → unique tail {row['hq']!r} (topology, not a relation choice)",
            f"opaque unique {fam_locked('factorial_2x2_iso', 'OPAQUE_UNIQUE', FAM_2X2)} — H1 not supported",
            "Topology determines the route. Not a claim that symbols are easy in general.",
            ok,
        ),
        Cell(
            "H5",
            "Two same-type routes + opaque relations (primary 2×2)",
            f"2 hops → tails {a_tails} ; engine with gold path still {plan_a}",
            (
                f"opaque two-path {fam_locked('factorial_2x2_iso', 'OPAQUE_AMBIG', FAM_2X2)}; "
                f"Eng two-path {fam_locked('factorial_2x2_iso', 'ENG_AMBIG', FAM_2X2)}; "
                f"OpenAI UNK {amb['unknown']} decoy {amb['decoy']}"
            ),
            "Failure is mostly UNKNOWN, not decoy. Selection is inferred from the answer, not scored (r1,r2). Listing shuffle is ORD.",
            ok,
        ),
        Cell(
            "H2",
            "Written hop / SealRouter (control)",
            f"SealRouter on ambig + gold rels → {plan_a}",
            f"plan {fam_locked('factorial_2x2_iso', 'OPAQUE_AMBIG_PLAN', FAM_2X2)}",
            "Execution control. Product PATH/JOIN is examples/middleware_hr.py — not this free cell.",
            ok and score(js, "OPAQUE_AMBIG_PLAN") == "32/32",
        ),
    ]


def cell_h3() -> Cell:
    ceil = load_mod("ceiling_three_arm_n32_iso")
    case = locked(ROOT / "results/ceiling_three_arm_n32_iso_harness.json")["cases"][0]
    person = case["person"]
    start = EntitySeal(ceil.item_key(0)).atom(person)
    nl = prompt("ceiling_three_arm_n32_iso", "SEAL_NL")
    prog = prompt("ceiling_three_arm_n32_iso", "SEAL_PROG")
    js = locked(ROOT / "results/ceiling_three_arm_n32_iso_gpt56.json")
    q = q_block(nl)
    atoms = [t for t in q.split() if HMAC.match(t.rstrip("?"))]
    start_in_q = start in q
    name_in_prompt = person in nl or person.replace("_", " ") in nl
    ok = (
        "PATH_QUERY" not in nl
        and "PATH_QUERY" in prog
        and len(atoms) >= 4
        and not start_in_q
        and not name_in_prompt
        and score(js, "SEAL_NL") == "0/32"
        and score(js, "SEAL_PROG") == "32/32"
    )
    return Cell(
        "H3",
        "CEO piecewise-hash NL (missing-start control)",
        (
            f"item 0 person {person!r}; start atom {start} absent from hashed q "
            f"({len(atoms)} HMAC tokens)"
        ),
        f"OpenAI SEAL_NL {score(js, 'SEAL_NL')} vs SEAL_PROG {score(js, 'SEAL_PROG')}",
        "Not a selection result. Start-in-q 2×2 is a different cell.",
        ok,
    )


def cell_h7() -> Cell:
    er = load_mod("entity_rel_2x2_iso")
    row, decoy = _picked_ceo(load_mod("factorial_2x2_iso"))
    sealer = EntitySeal(hashlib.sha256(er.KEY_BASE + b"0").digest()[:16])
    a = load_mod("factorial_2x2_iso").ambig_edges(row, decoy)
    oe = prompt("entity_rel_2x2_iso", "OE_AMBIG")
    oo = prompt("entity_rel_2x2_iso", "OO_AMBIG")
    js = locked(ROOT / "results/entity_rel_2x2_iso_gpt56.json")
    oe_eng = "works_at" in oe and "headquartered_in" in oe
    oo_eng = "works_at" not in oo.split("CONTEXT:")[-1]
    start = sealer.atom(row["person"])
    gold = sealer.atom(row["hq"])
    oo_edges = [(sealer.atom(h), sealer.atom(r), sealer.atom(t)) for h, r, t in a]
    plan = SealRouter(oo_edges).path(start, [sealer.atom("works_at"), sealer.atom("headquartered_in")])
    ok = (
        start in oe
        and start in oo
        and oe_eng
        and oo_eng
        and plan == [gold]
        and score(js, "OE_AMBIG") == "32/32"
        and score(js, "OO_AMBIG") == "1/32"
        and score(js, "OO_UNIQUE") == "32/32"
    )
    return Cell(
        "H7",
        "English relations + opaque entities vs both-opaque",
        f"OE context keeps works_at; OO seals both; gold path still {plan == [gold]}",
        (
            f"OE two-path {fam_locked('entity_rel_2x2_iso', 'OE_AMBIG', FAM_ER)}; "
            f"OO unique {fam_locked('entity_rel_2x2_iso', 'OO_UNIQUE', FAM_ER)}; "
            f"OO two-path {fam_locked('entity_rel_2x2_iso', 'OO_AMBIG', FAM_ER)}"
        ),
        "H7 is OpenAI-specific here (composer 28/32 OE two-path; Grok 3/32). Residual world knowledge on English names remains.",
        ok,
    )


def cell_h6() -> Cell:
    mq = load_mod("metaqa_2x2_iso")
    items = json.loads((ROOT / "data/metaqa/oir_2hop_people_n100.json").read_text())["items"]
    row, decoy = items[0], items[1]
    u, a = mq.unique_edges(row, decoy), mq.ambig_edges(row, decoy)
    hops = load_mod("factorial_2x2_iso").two_hops
    a_cond = prompt("metaqa_2x2_people_n100_iso", "OPAQUE_AMBIG")
    b_cond = prompt("metaqa_2x2_people_n100_qhash_iso", "OPAQUE_AMBIG")
    qa, qb = q_block(a_cond).lower(), q_block(b_cond).lower()
    js_b = locked(ROOT / "results/metaqa_2x2_people_n100_qhash_iso_gpt56.json")
    js_a = locked(ROOT / "results/metaqa_2x2_people_n100_iso_gpt56.json")
    leak_a = any(v in qa for v in LEAK_VERBS)
    leak_b = any(v in qb for v in LEAK_VERBS)
    banner_leak = any(v in b_cond.lower() for v in LEAK_VERBS)
    start_ok = f"[{row['actor']}]" in b_cond and row["actor"] in a_cond
    ok = (
        len(hops(u, row["actor"])) == 1
        and len(hops(a, row["actor"])) == 2
        and leak_a
        and not leak_b
        and not banner_leak
        and start_ok
        and score(js_b, "OPAQUE_UNIQUE") == "100/100"
        and score(js_b, "OPAQUE_AMBIG") == "3/100"
        and js_b["summary"]["OPAQUE_AMBIG"]["unknown"] == 87
        and js_b["summary"]["OPAQUE_AMBIG"]["decoy"] == 0
        and js_b["summary"]["OPAQUE_AMBIG"].get("both_named") == 10
        and score(js_a, "OPAQUE_AMBIG") == "96/100"
    )
    return Cell(
        "H6",
        "WikiMovies/MetaQA-derived n=100 Condition B",
        f"item 0 unique hops=1, two-path hops=2; actor {row['actor']!r} stays in q",
        (
            f"Cond B unique {score(js_b, 'OPAQUE_UNIQUE')} vs two-path {score(js_b, 'OPAQUE_AMBIG')} "
            f"(UNKNOWN {js_b['summary']['OPAQUE_AMBIG']['unknown']}, decoy 0, both-named 10); "
            f"Cond A two-path {score(js_a, 'OPAQUE_AMBIG')} leaks directed/starred"
        ),
        "Question verbs hashed; prompt headers name topology only. Condition A is not a selection result. OpenAI-only n=100 lock.",
        ok,
    )


def cell_h4() -> Cell:
    same = prompt("adv_induction_n32_iso", "SAME_TRAP")
    novel = prompt("adv_induction_n32_iso", "CROSS_TRAP")
    path = prompt("adv_induction_n32_iso", "PATH_TRAP")
    H = locked(ROOT / "results/adv_induction_n32_iso_harness.json")
    gold = next(c["gold"] for c in H["cases"] if c["id"] == "ADV32_SAME_TRAP_0")
    copy = last_demo_answer(same)
    demo_same, quiz_same = same.split("--- QUIZ ---", 1)
    demo_x, quiz_x = novel.split("--- QUIZ ---", 1)
    same_overlap = rel_atoms(demo_same) & rel_atoms(quiz_same)
    novel_only = rel_atoms(quiz_x) - rel_atoms(demo_x)
    js = locked(ROOT / "results/adv_induction_n32_iso_gpt56.json")
    cvb = locked(ROOT / "results/copy_vs_bind_n32_gpt56.json")
    ok = (
        bool(same_overlap)
        and bool(novel_only)
        and "PATH_QUERY" not in same
        and ("PATH_QUERY" in path or "START " in path)
        and copy != gold
        and bool(copy)
        and score(js, "SAME_TRAP") == "32/32"
        and score(js, "CROSS_TRAP") == "0/32"
        and cvb["summary"]["SAME_TRAP"]["copy_last_demo"] == "0/32"
        and cvb["summary"]["CROSS_TRAP"]["copy_last_demo"] == "0/32"
    )
    return Cell(
        "H4",
        "Matched vs novel demonstrations (dual-path)",
        (
            f"matched quiz shares {len(same_overlap)} demo rel tokens; "
            f"novel quiz has {len(novel_only)} rel tokens absent from demos; "
            f"last DEMO {copy} ≠ gold {gold}"
        ),
        (
            f"matched {fam_locked('adv_induction_n32_iso', 'SAME_TRAP', FAM_DP)}; "
            f"novel {fam_locked('adv_induction_n32_iso', 'CROSS_TRAP', FAM_DP)}; "
            f"copy-last-demo {cvb['summary']['SAME_TRAP']['copy_last_demo']}"
        ),
        "Reuse of shown seals, not reconstruction. Wording: demonstrations enable the corresponding joins.",
        ok,
    )


def cell_generators() -> Cell:
    fact = load_mod("factorial_2x2_iso")
    perm = load_mod("perm_2x2_iso")
    alpha = load_mod("alpha_2x2_iso")
    row, decoy = _picked_ceo(fact)
    a = fact.ambig_edges(row, decoy)
    hmac_tok = EntitySeal(fact.item_key(0)).atom("works_at")
    perm_tok = perm.PermSeal(perm.item_rng(0)).atom("works_at")
    alpha_tok = alpha.AlphaSeal(alpha.item_rng(0)).atom("works_at")
    js_h = locked(ROOT / "results/factorial_2x2_iso_gpt56.json")
    js_p = locked(ROOT / "results/perm_2x2_iso_gpt56.json")
    js_a = locked(ROOT / "results/alpha_2x2_iso_gpt56.json")
    hops = fact.two_hops(a, row["person"])
    ok = (
        HMAC.match(hmac_tok)
        and HMAC.match(perm_tok)
        and hmac_tok != perm_tok
        and not HMAC.match(alpha_tok)
        and len(hops) == 2
        and score(js_h, "OPAQUE_AMBIG") == "6/32"
        and score(js_p, "PERM_AMBIG") == "15/32"
        and score(js_a, "ALPHA_AMBIG") == "12/32"
    )
    return Cell(
        "GEN",
        "Generator robustness (direction, not magnitude)",
        f"HMAC {hmac_tok} vs perm {perm_tok} vs alpha {alpha_tok} on the same two-path graph",
        (
            f"two-path OpenAI HMAC {score(js_h, 'OPAQUE_AMBIG')}, "
            f"perm {score(js_p, 'PERM_AMBIG')}, alpha {score(js_a, 'ALPHA_AMBIG')}"
        ),
        "Instrument is not rate-invariant. Direction (unique ≫ two-path) is the claim.",
        ok,
    )


def cell_shuffle() -> Cell:
    h = locked(ROOT / "results/factorial_2x2_iso_shuffle_harness.json")
    js = locked(ROOT / "results/factorial_2x2_iso_shuffle_gpt56.json")
    ordj = locked(ROOT / "results/factorial_2x2_iso_shuffle_gpt56_order.json")
    p0 = prompt("factorial_2x2_iso_shuffle", "OPAQUE_AMBIG")
    n_gold = sum(1 for c in h["cases"] if c["gold_first"])
    amb = js["summary"]["OPAQUE_AMBIG"]
    ok = (
        n_gold == 16
        and h["n_decoy_first"] == 16
        and "gold-first" not in p0
        and "decoy-first" not in p0
        and "PATH_QUERY" not in p0
        and score(js, "ENG_AMBIG") == "29/32"
        and score(js, "OPAQUE_AMBIG") == "5/32"
        and amb["unknown"] == 25
        and amb["decoy"] == 1
        and ordj["by_arm"]["OPAQUE_AMBIG"]["gold_first"]["score"] == "3/16"
        and ordj["by_arm"]["OPAQUE_AMBIG"]["decoy_first"]["score"] == "2/16"
    )
    return Cell(
        "ORD",
        "Gold/decoy listing shuffle (OpenAI two-path)",
        "16 gold-first, 16 decoy-first; item 0 header does not name gold",
        (
            f"Eng {score(js, 'ENG_AMBIG')}; opaque {score(js, 'OPAQUE_AMBIG')} "
            f"(UNK {amb['unknown']} decoy {amb['decoy']}); "
            f"opaque gold-first {ordj['by_arm']['OPAQUE_AMBIG']['gold_first']['score']} vs "
            f"decoy-first {ordj['by_arm']['OPAQUE_AMBIG']['decoy_first']['score']}"
        ),
        "Primary lock stays gold-first 31→6. Decoy-first does not raise decoy.",
        ok,
    )


def cell_ident() -> Cell:
    rule = prompt("opaque_iso_json_n32", "ISO_RULE")
    silent = prompt("opaque_iso_json_n32", "ISO_SILENT")
    broken = prompt("opaque_iso_json_n32", "NS_SILENT")
    legend = prompt("seal_layer_legend/small_n32", "LEGEND")
    meta = prompt("seal_layer_legend/small_n32", "META")
    js = locked(ROOT / "results/opaque_iso_json_n32_harness_gpt56.json")
    js_l = locked(ROOT / "results/seal_layer_legend_small_n32_harness_gpt56.json")
    ok = (
        "Identical tokens" in rule
        and "Identical tokens" not in silent
        and "No JOIN" in rule
        and "JSONKEY" in broken
        and "KEY_SCHEMA" in legend
        and "PROTOCOL" in meta
        and score(js, "ISO_RULE") == "32/32"
        and score(js, "ISO_SILENT") == "6/32"
        and score(js, "NS_SILENT") == "0/32"
        and score(js_l, "LEGEND") == "0/32"
        and score(js_l, "META") == "32/32"
    )
    return Cell(
        "ID",
        "Identifiability without compiling JOIN",
        "ISO_RULE names equality; NS_SILENT namespaces keys so Q-token ≠ key; LEGEND is schema-only",
        (
            f"equality {score(js, 'ISO_RULE')}; silent same-σ {score(js, 'ISO_SILENT')}; "
            f"broken overlap {score(js, 'NS_SILENT')}; schema-only {score(js_l, 'LEGEND')}; "
            f"English protocol+schema {score(js_l, 'META')}"
        ),
        "Equality recipe is symbolic alignment, not English→seal binding. Secondary to the graph 2×2.",
        ok,
    )


def run() -> list[Cell]:
    fact = load_mod("factorial_2x2_iso")
    out = []
    out.extend(cells_2x2(fact))
    out.append(cell_h3())
    out.append(cell_h4())
    out.append(cell_h6())
    out.append(cell_h7())
    out.append(cell_generators())
    out.append(cell_shuffle())
    out.append(cell_ident())
    return out


def _print(cells: list[Cell]) -> None:
    print("OIR paper spine demo — item-0 construction + engine + locked JSON")
    print("Audit of the lock, not a re-run of n=32. SealRouter is the engine ceiling, not an LLM.\n")
    for c in cells:
        mark = "ok" if c.ok else "FAIL"
        print(f"[{mark}] {c.hid}  {c.title}")
        print(f"     engine: {c.engine}")
        print(f"     locked: {c.locked_score}")
        print(f"     note:   {c.note}\n")
    print("Not in this demo (appendix / packaging, not the 2×2 spine):")
    print("  Spider, FinQA, WTQ, Excel, hop-3/4, messy-doc. See the paper appendix.")
    print("Product middleware (H2-shaped PATH, names hidden): examples/middleware_hr.py")


def _live_openai() -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("\n--openai set but OPENAI_API_KEY missing; skip live MUT.")
        return
    try:
        from oir.chat import OpenAIChatClient

        model = os.environ.get("OIR_MODEL", "gpt-5.6-sol")
        client = OpenAIChatClient(model=model)
    except ImportError:
        print("\nInstall oir-layer[openai] for --openai.")
        return
    print(
        f"\nLive MUT on factorial item_0 only. Model={model}. "
        "This is not the locked n=32 gpt-5.6-sol cell."
    )
    for arm in ("OPAQUE_UNIQUE", "OPAQUE_AMBIG"):
        text = prompt("factorial_2x2_iso", arm)
        raw = client.complete([{"role": "user", "content": text}])
        line = raw.splitlines()[0] if raw else ""
        print(f"  {arm}: {line[:160]!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--openai",
        action="store_true",
        help="Send locked Wikidata 2×2 item_0 unique vs two-path MUT files. Not the n=32 lock.",
    )
    args = ap.parse_args()
    cells = run()
    _print(cells)
    if not all(c.ok for c in cells):
        raise SystemExit("paper spine demo failed")
    if args.openai:
        _live_openai()
    print("ok")


if __name__ == "__main__":
    main()
