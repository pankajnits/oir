#!/usr/bin/env python3
"""Build n=200 isolation suites. Does not rewrite any n=32/n=100 lock.

Wikidata people come from data/real/wikidata_ceo_hops_n200.json (QIDs + live
SPARQL verify). WikiMovies people come from data/metaqa/oir_2hop_people_n200.json
(n=100 freeze plus 100 extra KB rows).

  python3 harness/scale_n200.py              # freeze movies if needed, write all harnesses
  python3 harness/scale_n200.py wiki         # Wikidata suites only
  python3 harness/scale_n200.py movies       # WikiMovies suites only
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter, path_program  # noqa: E402
from oir.adapters import ceo_hq_edges, load_json_records  # noqa: E402
from paths import repo_rel  # noqa: E402

from ceiling_three_arm_n32_iso import pack_plain, pack_sealed  # noqa: E402
from factorial_2x2_iso import (  # noqa: E402
    ambig_edges,
    pack as wiki_pack,
    render as wiki_render,
    two_hops,
    unique_edges,
)
from header_decoy_ablation_iso import (  # noqa: E402
    ARMS as HEADER_ARMS,
    HEADERS,
    curve_decoy,
)
from metaqa_2x2_iso import (  # noqa: E402
    KB,
    ambig_edges as movie_ambig,
    candidates,
    pack as movie_pack,
    parse_kb,
    render as movie_render,
    unique_edges as movie_unique,
)
from metaqa_official_iso import hash_q_keep_entity  # noqa: E402

RESULTS = ROOT / "results"
N = 200
SEED = 20260915
WIKI = ROOT / "data" / "real" / "wikidata_ceo_hops_n200.json"
MOVIE_N100 = ROOT / "data" / "metaqa" / "oir_2hop_people_n100.json"
MOVIE_N200 = ROOT / "data" / "metaqa" / "oir_2hop_people_n200.json"
WIKI_KEY = b"oir-fact-2x2-iso-n200-v1"
OO_KEY = b"oir-entrel-2x2-iso-n200-v1"
CEIL_KEY = b"oir-ceil-n200-iso-v1"
MOVIE_KEY = b"oir-metaqa-2x2-people-n200-v1"
MOVIE_B_KEY = b"oir-metaqa-2x2-people-n200-qhash-v1"
DUAL_KEY = b"oir-dp-wikimovies-iso-n200-v1"
SHUFFLE_SEED = 20260915
LEAK = ("directed", "starred", "written", "writer", "director")


def wiki_rows() -> list[dict]:
    recs = load_json_records(WIKI)
    if len(recs) != N:
        raise SystemExit(f"{WIKI} has {len(recs)} rows; need {N}")
    return recs


def item_key(base: bytes, i: int) -> bytes:
    return hashlib.sha256(base + str(i).encode()).digest()[:16]


def clear(runs: Path) -> None:
    if runs.exists():
        for p in runs.rglob("prompt.txt"):
            p.unlink()
    runs.mkdir(parents=True, exist_ok=True)


def write_harness(name: str, obj: dict) -> dict:
    path = RESULTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    print("wrote", path, "n", obj.get("n"), flush=True)
    return obj


def build_wiki_h5() -> dict:
    picked = wiki_rows()
    runs = ROOT / "runs" / "factorial_2x2_iso_n200"
    clear(runs)
    arms = {a: {"ids": [], "item_paths": []} for a in (
        "ENG_UNIQUE", "ENG_AMBIG", "OPAQUE_UNIQUE", "OPAQUE_AMBIG", "OPAQUE_AMBIG_PLAN"
    )}
    cases = []
    for i, row in enumerate(picked):
        decoy = picked[(i + 1) % N]
        if decoy["hq"] == row["hq"] or decoy["person"] == row["person"]:
            raise ValueError(f"wiki-h5 item {i}: cyclic decoy shares hq/person")
        u_edges, a_edges = unique_edges(row, decoy), ambig_edges(row, decoy)
        EntitySeal.assert_raw_injective(x for e in (*u_edges, *a_edges) for x in e)
        u_hops, a_hops = two_hops(u_edges, row["person"]), two_hops(a_edges, row["person"])
        assert len(u_hops) == 1 and u_hops[0][2] == row["hq"]
        assert len(a_hops) == 2 and sum(h[2] == row["hq"] for h in a_hops) == 1
        sealer = EntitySeal(item_key(WIKI_KEY, i))
        q = f"What city is the headquarters of the company led by {row['person']}?"
        u_eng, a_eng = wiki_render(u_edges, None), wiki_render(a_edges, None)
        u_op, a_op = wiki_render(u_edges, sealer), wiki_render(a_edges, sealer)
        plan = path_program(
            row["person"],
            (sealer.atom("works_at"), sealer.atom("headquartered_in")),
            row["hq"],
        )
        gold_path = [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        assert SealRouter([(h, sealer.atom(r), t) for h, r, t in u_edges]).path(row["person"], gold_path) == [row["hq"]]
        assert SealRouter([(h, sealer.atom(r), t) for h, r, t in a_edges]).path(row["person"], gold_path) == [row["hq"]]
        specs = {
            "ENG_UNIQUE": (q, u_eng, "ARM ENG_UNIQUE: English relations; one 2-hop from start."),
            "ENG_AMBIG": (q, a_eng, "ARM ENG_AMBIG: English relations; two 2-hops from start."),
            "OPAQUE_UNIQUE": (q, u_op, "ARM OPAQUE_UNIQUE: opaque relations, English entities; one 2-hop from start."),
            "OPAQUE_AMBIG": (q, a_op, "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start."),
            "OPAQUE_AMBIG_PLAN": (
                q + "\n\n" + plan.body, a_op,
                "ARM OPAQUE_AMBIG_PLAN: same graph as OPAQUE_AMBIG plus explicit relation sequence.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"F200_{arm}_{i}"
            ids[arm] = cid
            path = runs / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(wiki_pack(cid, qq, ctx, sealed_ans=False, extra=header))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append({
            "i": i, "person": row["person"], "company": row["company"], "hq": row["hq"],
            "person_qid": row["person_qid"], "company_qid": row["company_qid"], "hq_qid": row["hq_qid"],
            "decoy_hq": decoy["hq"], "ids": ids, "gold": row["hq"],
        })
    return write_harness("factorial_2x2_iso_n200_harness.json", {
        "n": N, "seed": SEED, "protocol": "isolation",
        "source": str(WIKI.relative_to(ROOT)),
        "source_public": "Wikidata P169 CEO → P159 HQ, city-typed P31, n=200 freeze with QIDs",
        "keys": "per-item HMAC oir-fact-2x2-iso-n200-v1 on relation atoms; entities English",
        "start_in_question": True,
        "factors": ["relation_lexicality", "path_determinacy"],
        "n32_untouched": "runs/factorial_2x2_iso/",
        "arms": arms, "cases": cases,
    })


def build_header() -> dict:
    picked = wiki_rows()
    pool = picked
    runs = ROOT / "runs" / "header_decoy_ablation_iso_n200"
    clear(runs)
    arms = {
        name: {"ids": [], "item_paths": [], "header": hk, "decoy": dk,
               "relations": "opaque" if opaque else "english"}
        for name, hk, dk, opaque in HEADER_ARMS
    }
    cases = []
    for i, row in enumerate(picked):
        cyc = picked[(i + 1) % N]
        if cyc["hq"] == row["hq"] or cyc["person"] == row["person"]:
            raise ValueError(f"header item {i}: cyclic decoy shares hq/person")
        decoys = {"CYC": cyc, "CRV": curve_decoy(row, pool)}
        sealer = EntitySeal(item_key(WIKI_KEY, i))
        q = f"What city is the headquarters of the company led by {row['person']}?"
        case = {"i": i, "person": row["person"], "gold": row["hq"],
                "person_qid": row["person_qid"], "hq_qid": row["hq_qid"],
                "decoy_hq": {k: d["hq"] for k, d in decoys.items()}, "ids": {}}
        for name, hk, dk, opaque in HEADER_ARMS:
            edges = ambig_edges(row, decoys[dk])
            hops = two_hops(edges, row["person"])
            assert len(hops) == 2 and sum(h[2] == row["hq"] for h in hops) == 1
            cid = "H200_" + hashlib.sha256(
                b"oir-header-decoy-n200-v1" + name.encode() + b":" + str(i).encode()
            ).hexdigest()[:10]
            path = runs / name / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            ctx = wiki_render(edges, sealer if opaque else None)
            path.write_text(wiki_pack(cid, q, ctx, sealed_ans=False, extra=HEADERS[hk]))
            arms[name]["ids"].append(cid)
            arms[name]["item_paths"].append(repo_rel(path))
            case["ids"][name] = cid
        cases.append(case)
    return write_harness("header_decoy_ablation_iso_n200_harness.json", {
        "n": N, "seed": SEED, "protocol": "isolation",
        "suite": "header_decoy_ablation_iso_n200",
        "source": str(WIKI.relative_to(ROOT)),
        "keys": "same per-item HMAC as Wiki-H5 n=200 (oir-fact-2x2-iso-n200-v1)",
        "case_ids": "arm-neutral hashes (H200_…); no arm names in Format/ID lines",
        "factors": {"header": list(HEADERS), "decoy": ["CYC", "CRV"]},
        "n32_untouched": "runs/header_decoy_ablation_iso/",
        "arms": arms, "cases": cases,
    })


def build_entity_rel() -> dict:
    from entity_rel_2x2_iso import pack, render as er_render
    picked = wiki_rows()
    runs = ROOT / "runs" / "entity_rel_2x2_iso_n200"
    clear(runs)
    arm_names = ["OE_UNIQUE", "OE_AMBIG", "OO_UNIQUE", "OO_AMBIG", "OO_AMBIG_PLAN"]
    arms = {a: {"ids": [], "item_paths": [], "sealed_answer": True} for a in arm_names}
    cases = []
    for i, row in enumerate(picked):
        decoy = picked[(i + 1) % N]
        u_edges, a_edges = unique_edges(row, decoy), ambig_edges(row, decoy)
        assert len(two_hops(u_edges, row["person"])) == 1
        assert len(two_hops(a_edges, row["person"])) == 2
        sealer = EntitySeal(item_key(OO_KEY, i))
        start, gold, decoy_tok = sealer.atom(row["person"]), sealer.atom(row["hq"]), sealer.atom(decoy["hq"])
        q = f"What city is the headquarters of the company led by {start}?"
        oe_u = er_render(u_edges, sealer, seal_ent=True, seal_rel=False)
        oe_a = er_render(a_edges, sealer, seal_ent=True, seal_rel=False)
        oo_u = er_render(u_edges, sealer, seal_ent=True, seal_rel=True)
        oo_a = er_render(a_edges, sealer, seal_ent=True, seal_rel=True)
        plan = path_program(start, (sealer.atom("works_at"), sealer.atom("headquartered_in")), gold)
        specs = {
            "OE_UNIQUE": (q, oe_u, "ARM OE_UNIQUE: opaque entities, English relations; one 2-hop."),
            "OE_AMBIG": (q, oe_a, "ARM OE_AMBIG: opaque entities, English relations; two 2-hops."),
            "OO_UNIQUE": (q, oo_u, "ARM OO_UNIQUE: opaque entities and relations; one 2-hop; start seal in q."),
            "OO_AMBIG": (q, oo_a, "ARM OO_AMBIG: opaque entities and relations; two 2-hops; start seal in q."),
            "OO_AMBIG_PLAN": (
                q + "\n\n" + plan.body, oo_a,
                "ARM OO_AMBIG_PLAN: same OO_AMBIG graph plus explicit sealed relation sequence.",
            ),
        }
        ids, golds, decoys = {}, {}, {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"ER200_{arm}_{i}"
            ids[arm], golds[arm], decoys[arm] = cid, gold, decoy_tok
            path = runs / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, qq, ctx, header))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append({
            "i": i, "person": row["person"], "hq": row["hq"],
            "person_qid": row["person_qid"], "hq_qid": row["hq_qid"],
            "ids": ids, "gold": gold, "decoy_hq": decoy_tok, "golds": golds, "decoys": decoys,
        })
    return write_harness("entity_rel_2x2_iso_n200_harness.json", {
        "n": N, "seed": SEED, "protocol": "isolation",
        "source": str(WIKI.relative_to(ROOT)),
        "source_public": "Same n=200 Wikidata freeze as Wiki-H5; OE/OO entity sealing",
        "keys": "per-item HMAC oir-entrel-2x2-iso-n200-v1",
        "start_in_question": True,
        "n32_untouched": "runs/entity_rel_2x2_iso/",
        "arms": arms, "cases": cases,
    })


def build_shuffle() -> dict:
    from factorial_2x2_iso_shuffle import ordered_ambig_edges
    picked = wiki_rows()
    gold_first_idx = set(random.Random(SHUFFLE_SEED).sample(range(N), N // 2))
    runs = ROOT / "runs" / "factorial_2x2_iso_shuffle_n200"
    clear(runs)
    arms = {a: {"ids": [], "item_paths": []} for a in ("ENG_AMBIG", "OPAQUE_AMBIG")}
    cases = []
    for i, row in enumerate(picked):
        decoy = picked[(i + 1) % N]
        gold_first = i in gold_first_idx
        a_edges = ordered_ambig_edges(row, decoy, gold_first)
        hops = two_hops(a_edges, row["person"])
        assert len(hops) == 2
        first_tail = hops[0][2]
        assert first_tail == (row["hq"] if gold_first else decoy["hq"])
        sealer = EntitySeal(item_key(WIKI_KEY, i))
        q = f"What city is the headquarters of the company led by {row['person']}?"
        specs = {
            "ENG_AMBIG": (q, wiki_render(a_edges, None), "ARM ENG_AMBIG: English relations; two 2-hops from start."),
            "OPAQUE_AMBIG": (q, wiki_render(a_edges, sealer), "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start."),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"F200S_{arm}_{i}"
            ids[arm] = cid
            path = runs / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(wiki_pack(cid, qq, ctx, sealed_ans=False, extra=header))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append({
            "i": i, "person": row["person"], "hq": row["hq"], "decoy_hq": decoy["hq"],
            "gold_first": gold_first, "ids": ids, "gold": row["hq"],
        })
    return write_harness("factorial_2x2_iso_shuffle_n200_harness.json", {
        "n": N, "seed": SEED, "shuffle_seed": SHUFFLE_SEED, "protocol": "isolation",
        "source": str(WIKI.relative_to(ROOT)),
        "keys": "same HMAC as Wiki-H5 n=200; CONTEXT listing order shuffled",
        "n_gold_first": N // 2, "n_decoy_first": N // 2,
        "n32_untouched": "runs/factorial_2x2_iso_shuffle/",
        "arms": arms, "cases": cases,
    })


def build_ceiling() -> dict:
    picked = wiki_rows()
    runs = ROOT / "runs" / "ceiling_three_arm_n200_iso"
    clear(runs)
    arms = {a: {"ids": [], "item_paths": []} for a in ("PLAIN_PROG", "SEAL_PROG", "SEAL_NL")}
    cases = []
    for i, row in enumerate(picked):
        sealer = EntitySeal(item_key(CEIL_KEY, i))
        person, hq, company = row["person"], row["hq"], row["company"]
        edges = ceo_hq_edges(row)
        plain_ctx = SealRouter(edges).render()
        sealed_triples = [sealer.triple(*e) for e in edges]
        sealed_ctx = SealRouter(sealed_triples).render()
        outs = SealRouter(sealed_triples).path(
            sealer.atom(person), [sealer.atom("works_at"), sealer.atom("headquartered_in")]
        )
        assert list(dict.fromkeys(outs)) == [sealer.atom(hq)]
        prog_plain = path_program(person, ("works_at", "headquartered_in"), hq)
        prog_sealed = prog_plain.seal(sealer)
        q = f"Where is the headquarters of the company that {person.replace('_', ' ')} works for?"
        cid_a, cid_b, cid_c = f"CEIL200_PLAIN_{i}", f"CEIL200_SEALPROG_{i}", f"CEIL200_SEALNL_{i}"
        pa = runs / "PLAIN_PROG" / f"item_{i}" / "prompt.txt"
        pb = runs / "SEAL_PROG" / f"item_{i}" / "prompt.txt"
        pc = runs / "SEAL_NL" / f"item_{i}" / "prompt.txt"
        for p in (pa, pb, pc):
            p.parent.mkdir(parents=True, exist_ok=True)
        pa.write_text(pack_plain(cid_a, prog_plain.body, plain_ctx))
        pb.write_text(pack_sealed(cid_b, prog_sealed.body, sealed_ctx, "ARM B: same PATH binder with opaque sealed atoms."))
        pc.write_text(pack_sealed(cid_c, f"QUESTION:\n{sealer.text(q)}", sealed_ctx, "ARM C: sealed free NL — no program."))
        arms["PLAIN_PROG"]["ids"].append(cid_a)
        arms["PLAIN_PROG"]["item_paths"].append(repo_rel(pa))
        arms["SEAL_PROG"]["ids"].append(cid_b)
        arms["SEAL_PROG"]["item_paths"].append(repo_rel(pb))
        arms["SEAL_NL"]["ids"].append(cid_c)
        arms["SEAL_NL"]["item_paths"].append(repo_rel(pc))
        cases.append({
            "i": i, "person": person, "company": company, "hq": hq,
            "person_qid": row["person_qid"], "hq_qid": row["hq_qid"],
            "id_plain": cid_a, "id_sealprog": cid_b, "id_sealnl": cid_c,
            "expect_plain": hq, "expect_seal": sealer.atom(hq), "company_seal": sealer.atom(company),
        })
    return write_harness("ceiling_three_arm_n200_iso_harness.json", {
        "n": N, "seed": SEED, "protocol": "isolation", "keys": "per-item HMAC oir-ceil-n200-iso-v1",
        "source": str(WIKI.relative_to(ROOT)), "sealrouter_ceiling": f"{N}/{N}",
        "n32_untouched": "runs/ceiling_three_arm_n32_iso/",
        "arms": arms, "cases": cases,
    })


def freeze_movies() -> list[dict]:
    if not KB.exists():
        raise SystemExit(f"Download WikiMovies KB to {KB}")
    keep = json.loads(MOVIE_N100.read_text())["items"]
    assert len(keep) == 100
    seen_act = {r["actor"] for r in keep}
    seen_am = {(r["actor"], r["movie"]) for r in keep}
    movies = parse_kb(KB)
    extra = [r for r in candidates(movies)
             if (r["actor"], r["movie"]) not in seen_am and r["actor"] not in seen_act]
    extra_u, extra_act = [], set()
    rng = random.Random(SEED)
    rng.shuffle(extra)
    for r in extra:
        if r["actor"] in extra_act:
            continue
        extra_u.append(r)
        extra_act.add(r["actor"])
    need = N - len(keep)
    if need > len(extra_u):
        raise SystemExit(f"need {need} extra unique actors, have {len(extra_u)}")
    picked = keep + extra_u[:need]
    assert len({r["actor"] for r in picked}) == N
    MOVIE_N200.write_text(json.dumps({
        "seed": SEED, "n": N,
        "prefix": "oir_2hop_people_n100.json first 100, then 100 new unique actors from wiki_entities_kb.txt",
        "kb": "data/metaqa/wiki_entities_kb.txt",
        "items": picked,
    }, indent=2, ensure_ascii=False) + "\n")
    print("wrote", MOVIE_N200, "n", N, flush=True)
    return picked


def movie_rows() -> list[dict]:
    if not MOVIE_N200.exists():
        return freeze_movies()
    items = json.loads(MOVIE_N200.read_text())["items"]
    if len(items) != N:
        return freeze_movies()
    return items


def build_movie_a() -> dict:
    picked = movie_rows()
    runs = ROOT / "runs" / "metaqa_2x2_people_n200_iso"
    clear(runs)
    arm_names = ["ENG_UNIQUE", "ENG_AMBIG", "OPAQUE_UNIQUE", "OPAQUE_AMBIG", "OPAQUE_AMBIG_PLAN"]
    arms = {a: {"ids": [], "item_paths": []} for a in arm_names}
    cases = []
    for i, row in enumerate(picked):
        decoy = next(
            picked[(i + k) % N]
            for k in range(1, N)
            if picked[(i + k) % N]["actor"] != row["actor"]
            and picked[(i + k) % N]["movie"] != row["movie"]
        )
        u_edges = movie_unique(row, decoy)
        a_edges = list(dict.fromkeys(movie_ambig(row, decoy)))
        assert len(two_hops(u_edges, row["actor"])) == 1
        assert len(two_hops(a_edges, row["actor"])) == 2
        sealer = EntitySeal(item_key(MOVIE_KEY, i))
        q = f"Who directed a movie that {row['actor']} starred in?"
        plan = path_program(row["actor"], (sealer.atom("starred_in"), sealer.atom("directed_by")), row["director"])
        specs = {
            "ENG_UNIQUE": (q, movie_render(u_edges, None), "ARM ENG_UNIQUE: English relations; one 2-hop from start."),
            "ENG_AMBIG": (q, movie_render(a_edges, None), "ARM ENG_AMBIG: English relations; two 2-hops from start."),
            "OPAQUE_UNIQUE": (q, movie_render(u_edges, sealer), "ARM OPAQUE_UNIQUE: opaque relations, English entities; one 2-hop from start."),
            "OPAQUE_AMBIG": (q, movie_render(a_edges, sealer), "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start."),
            "OPAQUE_AMBIG_PLAN": (
                q + "\n\n" + plan.body, movie_render(a_edges, sealer),
                "ARM OPAQUE_AMBIG_PLAN: same graph as OPAQUE_AMBIG plus explicit relation sequence.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"MQA200_{arm}_{i}"
            ids[arm] = cid
            path = runs / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(movie_pack(cid, qq, ctx, header))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append({**row, "i": i, "ids": ids, "gold": row["director"], "decoy_hq": row["writer"]})
    return write_harness("metaqa_2x2_people_n200_iso_harness.json", {
        "n": N, "seed": SEED, "protocol": "isolation",
        "source": "WikiMovies kb; n=200 = n=100 freeze plus 100 new unique actors",
        "source_url": "https://github.com/rohit129/Movie_KnowledgeGraph_QA/blob/master/wiki_entities_kb.txt",
        "freeze": str(MOVIE_N200.relative_to(ROOT)),
        "start_in_question": True,
        "n100_untouched": "runs/metaqa_2x2_people_n100_iso/",
        "arms": arms, "cases": cases,
    })


def build_movie_b() -> dict:
    picked = movie_rows()
    runs = ROOT / "runs" / "metaqa_2x2_people_n200_qhash_iso"
    clear(runs)
    arm_names = ["OPAQUE_UNIQUE", "OPAQUE_AMBIG", "OPAQUE_AMBIG_PLAN"]
    arms = {a: {"ids": [], "item_paths": []} for a in arm_names}
    cases = []
    for i, row in enumerate(picked):
        decoy = next(
            picked[(i + k) % N]
            for k in range(1, N)
            if picked[(i + k) % N]["actor"] != row["actor"]
            and picked[(i + k) % N]["movie"] != row["movie"]
        )
        u_edges = movie_unique(row, decoy)
        a_edges = list(dict.fromkeys(movie_ambig(row, decoy)))
        sealer = EntitySeal(item_key(MOVIE_B_KEY, i))
        q_raw = f"Who directed a movie that [{row['actor']}] starred in?"
        q = hash_q_keep_entity(q_raw, row["actor"], sealer)
        q_head = q.split("CONTEXT:")[0].lower()
        for w in LEAK:
            if w in q_head:
                raise SystemExit(f"verb leak in hashed question item {i}: {q!r}")
        plan = path_program(row["actor"], (sealer.atom("starred_in"), sealer.atom("directed_by")), row["director"])
        specs = {
            "OPAQUE_UNIQUE": (q, movie_render(u_edges, sealer), "ARM OPAQUE_UNIQUE: opaque relations, English entities; one 2-hop from start."),
            "OPAQUE_AMBIG": (q, movie_render(a_edges, sealer), "ARM OPAQUE_AMBIG: opaque relations, English entities; two 2-hops from start."),
            "OPAQUE_AMBIG_PLAN": (
                q + "\n\n" + plan.body, movie_render(a_edges, sealer),
                "ARM OPAQUE_AMBIG_PLAN: opaque relations, English entities; two 2-hops from start; explicit join plan.",
            ),
        }
        ids = {}
        for arm, (qq, ctx, header) in specs.items():
            cid = f"MQA200B_{arm}_{i}"
            ids[arm] = cid
            path = runs / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(movie_pack(cid, qq, ctx, header))
            blob = path.read_text().lower()
            for w in LEAK:
                if w in blob:
                    raise SystemExit(f"verb leak in {arm} item {i}: {w!r}")
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append({**row, "i": i, "ids": ids, "gold": row["director"], "decoy_hq": row["writer"]})
    return write_harness("metaqa_2x2_people_n200_qhash_iso_harness.json", {
        "n": N, "seed": SEED, "protocol": "isolation", "condition": "B",
        "source": "WikiMovies / MetaQA; same 200 items as Condition A n=200 freeze",
        "freeze": str(MOVIE_N200.relative_to(ROOT)),
        "n100_untouched": "runs/metaqa_2x2_people_n100_qhash_iso/",
        "arms": arms, "cases": cases,
    })


def build_dual() -> dict:
    from dualpath_wikimovies_iso import (
        ARMS, N_DEMO, ambig_edges, demo_block, novel_ambig_edges, pack,
    )
    picked = movie_rows()
    runs = ROOT / "runs" / "dualpath_wikimovies_iso_n200"
    clear(runs)
    arms = {a: {"ids": [], "item_paths": [], "sealed_answer": True} for a in ARMS}
    cases = []
    n = len(picked)
    for i, row in enumerate(picked):
        sealer = EntitySeal(item_key(DUAL_KEY, i))
        demos = [picked[(i + 1 + j) % n] for j in range(N_DEMO)]
        blocks = "\n\n".join(demo_block(j, d, sealer) for j, d in enumerate(demos))
        preamble = (
            "Learn the mapping from DEMOs (same encoding).\n"
            "Answer the QUIZ the same way. No English relation names. No PATH.\n"
            "If ambiguous, UNKNOWN.\n\n" + blocks + "\n\n--- QUIZ ---\n"
        )
        start, gold, trap = sealer.atom(row["actor"]), sealer.atom(row["director"]), sealer.atom(row["writer"])
        matched_sealed = [sealer.triple(*e) for e in ambig_edges(row)]
        novel_sealed = [sealer.triple(*e) for e in novel_ambig_edges(row)]
        m_ctx, n_ctx = SealRouter(matched_sealed).render(), SealRouter(novel_sealed).render()
        plan = path_program(start, (sealer.atom("starred_in"), sealer.atom("directed_by")), gold)
        specs = {
            "MATCHED": (
                "ARM MATCHED: demos expose gold relation seals; quiz has a decoy path.",
                preamble + f"##### ID DP200_MATCHED_{i} #####\nSTART {start}\nCONTEXT:\n{m_ctx}\n",
            ),
            "NOVEL": (
                "ARM NOVEL: demo seals do not appear on the quiz gold route.",
                preamble + f"##### ID DP200_NOVEL_{i} #####\nSTART {start}\nCONTEXT:\n{n_ctx}\n",
            ),
            "PLAN": (
                "ARM PLAN: explicit sealed relation sequence on the MATCHED graph.",
                "Follow PATH over sealed CONTEXT. Output final sealed atom only.\n\n"
                f"##### ID DP200_PLAN_{i} #####\n{plan.body}\n\nCONTEXT:\n{m_ctx}\n",
            ),
        }
        ids = {}
        for arm, (header, body) in specs.items():
            cid = f"DP200_{arm}_{i}"
            ids[arm] = cid
            path = runs / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(pack(cid, header, body))
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))
        cases.append({
            "i": i, "actor": row["actor"], "movie": row["movie"], "ids": ids,
            "gold": gold, "decoy_hq": trap, "golds": {a: gold for a in ARMS}, "decoys": {a: trap for a in ARMS},
        })
    return write_harness("dualpath_wikimovies_iso_n200_harness.json", {
        "n": n, "seed": SEED, "protocol": "isolation",
        "source": str(MOVIE_N200.relative_to(ROOT)),
        "n32_untouched": "runs/dualpath_wikimovies_iso/",
        "arms": arms, "cases": cases,
    })


def build_wiki() -> None:
    if not WIKI.exists():
        raise SystemExit("run python3 harness/fetch_wikidata_ceo_n200.py first")
    build_wiki_h5()
    build_header()
    build_entity_rel()
    build_shuffle()
    build_ceiling()


def build_movies() -> None:
    freeze_movies()
    build_movie_a()
    build_movie_b()
    build_dual()


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "wiki"):
        build_wiki()
    if which in ("all", "movies"):
        build_movies()


if __name__ == "__main__":
    main()
