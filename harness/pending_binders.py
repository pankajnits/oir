#!/usr/bin/env python3
"""Pending 26 Aug variations: equality recipe off CEO-JSON, n=6 isolation.

Arms
  VAULT_EQ  — HMAC table headers = same σ as Q; values shown; equality recipe; no JOIN
  SQL_EQ    — bilingual schema (English name = sealed id); no rows; same-σ Q↔country;
              leaf has city and country (city is trap); we execute SQL
  SQL_NS    — same bilingual schema; SQLCOL: namespace so Q token ≠ country seal
  WM_EQ     — WikiMovies director vs writer; same-σ Q; equality recipe; no plan
  WM_SILENT — same graph; no recipe

Not the matched 2×2. Not JOIN n=32. Not WikiMovies n=100. Not confidentiality.
Seed 20260902.
"""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from oir import EntitySeal, SealRouter
from oir.adapters import load_ceo_hq_graph
from grev1_fullq_prog import country_of, seal_question
from paths import repo_abs, repo_rel
from seal_layer_legend import leak_check, pack
from wilson_cis import wilson

RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "pending_binders"
SEED = 20260902
N = 6
WM_FREEZE = ROOT / "data" / "metaqa" / "oir_2hop_people_n32.json"
SEAL = re.compile(r"ANSWER_SEALED\[([^\]]+)\]:\s*(\S+)", re.I)
SQL_RX = re.compile(r"SQL\[([^\]]+)\]:\s*(.+?)(?=\nSQL\[|\nANSWER_|\n#####|\Z)", re.I | re.S)
ATOM = re.compile(r"E[0-9a-f]{12}", re.I)

EQ = """
PROTOCOL (English; do not decrypt):
- QUESTION, SCHEMA, and CONTEXT (if present) use the same encoding.
- Identical tokens are the same entity or the same field (equality, not English).
- Walk by token equality. If more than one reading is possible, UNKNOWN.
No JOIN/PATH is given.
""".strip()

SQL_PROTO = """
PROTOCOL (English; do not decrypt):
- The context is this file only: QUESTION + SCHEMA. There are no data rows.
- Do not use world knowledge. Do not decrypt.
- SCHEMA is bilingual: English name = sealed sqlite table or column.
- A sealed QUESTION token that equals a SCHEMA identifier is that column.
- A sealed QUESTION token that does not appear in SCHEMA is an emp_id value.
- Join tables on column names that appear in two tables.
- Write ONE sqlite SELECT using the sealed identifiers. We execute it on hidden rows.
- If no QUESTION token equals a column, or more than one reading is possible, output UNKNOWN.
""".strip()


def qid(name: str) -> str:
    return f'"{name}"'


def gold_sql(tmap: dict, cmap: dict, emp_id: str) -> str:
    te, to, tc = (qid(tmap[k]) for k in ("employees", "orgs", "cities"))
    e, o, c, n = (qid(cmap[k]) for k in ("emp_id", "org_id", "city_id", "country"))
    return (
        f"SELECT {tc}.{n} FROM {te} "
        f"JOIN {to} ON {te}.{o} = {to}.{o} "
        f"JOIN {tc} ON {to}.{c} = {tc}.{c} "
        f"WHERE {te}.{e} = '{emp_id}'"
    )


def build_db(path: Path, tmap, cmap, emp_rows, org_rows, city_rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    te, to, tc = tmap["employees"], tmap["orgs"], tmap["cities"]
    e, o, ci, city, n = (
        cmap["emp_id"],
        cmap["org_id"],
        cmap["city_id"],
        cmap["city"],
        cmap["country"],
    )
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE {qid(te)} ({qid(e)} TEXT, {qid(o)} TEXT)")
    con.execute(f"CREATE TABLE {qid(to)} ({qid(o)} TEXT, {qid(ci)} TEXT)")
    con.execute(
        f"CREATE TABLE {qid(tc)} ({qid(ci)} TEXT, {qid(city)} TEXT, {qid(n)} TEXT)"
    )
    con.executemany(f"INSERT INTO {qid(te)} VALUES (?, ?)", emp_rows)
    con.executemany(f"INSERT INTO {qid(to)} VALUES (?, ?)", org_rows)
    con.executemany(f"INSERT INTO {qid(tc)} VALUES (?, ?, ?)", city_rows)
    con.commit()
    con.close()


def exec_sql(db: Path, sql: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def schema_text(tmap, cmap) -> str:
    pairs = [
        ("employees", tmap["employees"]),
        ("orgs", tmap["orgs"]),
        ("cities", tmap["cities"]),
        ("emp_id", cmap["emp_id"]),
        ("org_id", cmap["org_id"]),
        ("city_id", cmap["city_id"]),
        ("city", cmap["city"]),
        ("country", cmap["country"]),
    ]
    legend = "\n".join(f"{en} = {seal}" for en, seal in pairs)
    shape = (
        "employees(emp_id, org_id)\n"
        "orgs(org_id, city_id)\n"
        "cities(city_id, city, country)"
    )
    return (
        "SCHEMA (English name → sealed sqlite identifier):\n"
        f"{legend}\n\n"
        f"{shape}\n"
    )


def q_atoms(q: str) -> set[str]:
    return set(ATOM.findall(q))


def schema_atoms(tmap, cmap) -> set[str]:
    return set(ATOM.findall(schema_text(tmap, cmap)))


def normalize_sql(sql: str) -> str:
    sql = re.sub(r"\s+", " ", sql or "").strip().rstrip(";")
    sql = re.split(r"\s+#", sql, 1)[0].strip()
    return sql


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([line, sep, *body])


def build() -> dict:
    graph = load_ceo_hq_graph(ROOT / "data/real/wikidata_ceo_hops_v2.json")
    rng = random.Random(SEED)
    recs = rng.sample(graph.records, N)
    pool = [r for r in graph.records if r not in recs]
    wm_all = json.loads(WM_FREEZE.read_text())["items"]
    wm = [x for x in wm_all if x["director"] != x["writer"]]
    rng_wm = random.Random(SEED + 1)
    wm_recs = rng_wm.sample(wm, N)

    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
        for p in RUNS.rglob("*.sqlite"):
            p.unlink()

    arms = {
        a: {"ids": [], "item_paths": [], "sealed_answer": a not in ("SQL_EQ", "SQL_NS")}
        for a in ("VAULT_EQ", "SQL_EQ", "SQL_NS", "WM_EQ", "WM_SILENT")
    }
    cases = []

    for i, row in enumerate(recs):
        person, company, hq = row["person"], row["company"], row["hq"]
        country = country_of(hq)
        display = person.replace("_", " ")
        others = rng.sample(pool, 2)
        sealer = EntitySeal(rng.randbytes(16))
        pS, cS, hS, nS = (sealer.atom(x) for x in (person, company, hq, country))
        names = (
            person,
            display,
            company,
            hq,
            country,
            *[d["person"].replace("_", " ") for d in others],
        )

        # same-σ maps (Q word == column/header)
        iso = {
            "employees": sealer.atom("employees"),
            "orgs": sealer.atom("orgs"),
            "cities": sealer.atom("cities"),
            "id": sealer.atom("id"),
            "emp_id": sealer.atom("emp_id"),
            "org_id": sealer.atom("org_id"),
            "city_id": sealer.atom("city_id"),
            "employer": sealer.atom("employer"),
            "city": sealer.atom("city"),
            "country": sealer.atom("country"),
        }
        ns = {k: sealer.atom(f"SQLCOL:{k}") for k in iso}

        emp_rows = [(pS, cS)]
        org_rows = [(cS, hS)]
        city_rows = [(hS, hS, nS)]
        emp_md = [[pS, cS]]
        org_md = [[cS, hS, nS]]
        for d in others:
            dc = country_of(d["hq"])
            dh = sealer.atom(d["hq"])
            emp_rows.append((sealer.atom(d["person"]), sealer.atom(d["company"])))
            org_rows.append((sealer.atom(d["company"]), dh))
            city_rows.append((dh, dh, sealer.atom(dc)))
            emp_md.append([sealer.atom(d["person"]), sealer.atom(d["company"])])
            org_md.append([sealer.atom(d["company"]), dh, sealer.atom(dc)])
        rng.shuffle(emp_rows)
        rng.shuffle(org_rows)
        rng.shuffle(city_rows)
        rng.shuffle(emp_md)
        rng.shuffle(org_md)

        tmap = {k: iso[k] for k in ("employees", "orgs", "cities")}
        cmap_iso = {
            k: iso[k] for k in ("emp_id", "org_id", "city_id", "city", "country")
        }
        cmap_ns = {
            k: ns[k] for k in ("emp_id", "org_id", "city_id", "city", "country")
        }
        tmap_ns = {k: ns[k] for k in ("employees", "orgs", "cities")}

        db_iso = RUNS / "db" / f"iso_{i}.sqlite"
        db_ns = RUNS / "db" / f"ns_{i}.sqlite"
        build_db(db_iso, tmap, cmap_iso, emp_rows, org_rows, city_rows)
        build_db(db_ns, tmap_ns, cmap_ns, emp_rows, org_rows, city_rows)
        gsql_iso = gold_sql(tmap, cmap_iso, pS)
        gsql_ns = gold_sql(tmap_ns, cmap_ns, pS)
        assert exec_sql(db_iso, gsql_iso)[0][0] == nS
        assert exec_sql(db_ns, gsql_ns)[0][0] == nS
        trap_iso = gold_sql(tmap, {**cmap_iso, "country": cmap_iso["city"]}, pS)
        trap_ns = gold_sql(tmap_ns, {**cmap_ns, "country": cmap_ns["city"]}, pS)
        assert exec_sql(db_iso, trap_iso)[0][0] == hS
        assert exec_sql(db_ns, trap_ns)[0][0] == hS

        q_iso = seal_question(f"What is the country of {pS}?", sealer, {pS})
        q_sql = f"What is the {iso['country']} of {pS}?"
        qa = q_atoms(q_sql)
        assert qa == {iso["country"], pS}
        assert qa & schema_atoms(tmap, cmap_iso) == {iso["country"]}
        assert qa & schema_atoms(tmap_ns, cmap_ns) == set()
        assert iso["city"] not in qa
        assert pS not in schema_atoms(tmap, cmap_iso)

        vault_ctx = "\n".join(
            [
                f"TABLE {iso['employees']}",
                md_table([iso["id"], iso["employer"]], emp_md),
                "",
                f"TABLE {iso['orgs']}",
                md_table([iso["id"], iso["city"], iso["country"]], org_md),
            ]
        )
        vpath = RUNS / "VAULT_EQ" / f"item_{i}" / "prompt.txt"
        vbody = pack(
            f"PB_VAULT_EQ_{i}",
            "ARM VAULT_EQ: sealed markdown tables; same σ as Q; equality recipe; no JOIN.",
            q_iso,
            EQ + "\n",
            vault_ctx,
        )
        assert not leak_check(vbody, *names)
        assert not re.search(r"\b(start|emp_id)\b", vbody, re.I)
        vpath.parent.mkdir(parents=True, exist_ok=True)
        vpath.write_text(vbody)

        def sql_prompt(_cid, t_map, c_map, dbp, gsql):
            cid_show = f"PB_SQL_{i}"
            body = (
                f"##### ID {cid_show} #####\n"
                f"{schema_text(t_map, c_map)}\n"
                "QUESTION:\n"
                f"{q_sql}\n\n"
                f"{SQL_PROTO}\n"
            )
            text = (
                "MODEL UNDER TEST. Read ONLY this file. The schema is the context. "
                "No decrypt. No world knowledge. Do not open other files.\n"
                f"Format: SQL[{cid_show}]: <sqlite>\n"
                "If more than one reading is possible, output UNKNOWN.\n\n"
                "Sealed question. Schema maps English names to sealed identifiers. No rows.\n\n"
                f"{body}"
            )
            assert not leak_check(text, *names)
            assert not re.search(r"\b(start|namespace|sqlcol)\b", text, re.I)
            return {
                "text": text,
                "db": repo_rel(dbp),
                "gold_sql": gsql,
            }

        sp_eq = sql_prompt(f"PB_SQL_EQ_{i}", tmap, cmap_iso, db_iso, gsql_iso)
        sp_ns = sql_prompt(f"PB_SQL_NS_{i}", tmap_ns, cmap_ns, db_ns, gsql_ns)
        pe = RUNS / "SQL_EQ" / f"item_{i}" / "prompt.txt"
        pn = RUNS / "SQL_NS" / f"item_{i}" / "prompt.txt"
        pe.parent.mkdir(parents=True, exist_ok=True)
        pn.parent.mkdir(parents=True, exist_ok=True)
        pe.write_text(sp_eq["text"])
        pn.write_text(sp_ns["text"])

        recs_common = dict(
            i=i,
            gold=nS,
            trap=hS,
            start=pS,
            iso=True,
            per_item_key=True,
            plaintext_in_prompt=False,
            app_q=f"What is the country of {display}?",
        )
        specs = [
            ("VAULT_EQ", f"PB_VAULT_EQ_{i}", repo_rel(vpath), None, None),
            ("SQL_EQ", f"PB_SQL_EQ_{i}", repo_rel(pe), sp_eq["db"], sp_eq["gold_sql"]),
            ("SQL_NS", f"PB_SQL_NS_{i}", repo_rel(pn), sp_ns["db"], sp_ns["gold_sql"]),
        ]
        for arm, cid, path, db, gsql in specs:
            rec = {
                **recs_common,
                "arm": arm,
                "id": cid,
                "path": path,
                "surface": "sql" if arm.startswith("SQL") else "vault",
            }
            if db:
                rec["db"] = db
                rec["gold_sql"] = gsql
            cases.append(rec)
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(path)

    for i, row in enumerate(wm_recs):
        sealer = EntitySeal(rng_wm.randbytes(16))
        actor, movie = row["actor"], row["movie"]
        director, writer = row["director"], row["writer"]
        aS, mS, dS, wS = (sealer.atom(x) for x in (actor, movie, director, writer))
        r_star = sealer.atom("starred_in")
        r_dir = sealer.atom("directed_by")
        r_wri = sealer.atom("written_by")
        edges = [
            (aS, r_star, mS),
            (mS, r_dir, dS),
            (mS, r_wri, wS),
        ]
        ctx = SealRouter(edges).render()
        start = aS
        q = seal_question(
            f"What is the directed_by of the starred_in of {start}?",
            sealer,
            {start},
        )
        assert r_dir in ATOM.findall(q)
        assert r_star in ATOM.findall(q)
        names = (actor, movie, director, writer)
        for arm, extra, header in (
            (
                "WM_EQ",
                EQ + "\n",
                "ARM WM_EQ: WikiMovies two-route graph; equality recipe; no plan.",
            ),
            (
                "WM_SILENT",
                "",
                "ARM WM_SILENT: same two-route WikiMovies graph; no recipe; no plan.",
            ),
        ):
            cid = f"PB_{arm}_{i}"
            body = pack(cid, header, q, extra, ctx)
            assert not leak_check(body, *names)
            assert not re.search(r"\bstart\b", body, re.I)
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            rec = {
                "arm": arm,
                "i": i,
                "id": cid,
                "gold": dS,
                "trap": wS,
                "start": start,
                "path": repo_rel(path),
                "iso": True,
                "surface": "wikimovies",
                "plaintext_in_prompt": False,
                "app_q": f"Who directed the movie {actor} starred in?",
            }
            cases.append(rec)
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

    h = {
        "n": N,
        "suite": "pending_binders",
        "seed": SEED,
        "protocol": "isolation; per-item HMAC; no compiled JOIN",
        "nonclaim": (
            "Follow-up probes, not the Wikidata 2×2. SQL hides rows; city vs country "
            "are sibling leaf columns. WM is director vs writer. "
            "JOIN n=32 and WikiMovies n=100 are not this suite. Not confidentiality."
        ),
        "arms": arms,
        "cases": cases,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "pending_binders_harness.json"
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False))
    print(json.dumps({"n": N, "arms": list(arms), "out": str(out)}, indent=2))
    return h


def parse_replies(tag: str) -> tuple[dict[str, str], dict[str, str]]:
    d = RESULTS / f"pending_binders_harness_replies_{tag}"
    seals, sqls = {}, {}
    if not d.exists():
        return seals, sqls
    for p in d.rglob("*.txt"):
        text = p.read_text()
        seals.update({m.group(1): m.group(2).strip() for m in SEAL.finditer(text)})
        tagged = list(SQL_RX.finditer(text))
        if p.parent.name in ("SQL_EQ", "SQL_NS"):
            idx = p.stem.split("_")[-1]
            cid = f"PB_{p.parent.name}_{idx}"
            if tagged:
                sqls[cid] = normalize_sql(tagged[-1].group(2))
            elif re.search(r"\bUNKNOWN\b", text, re.I) and "SELECT" not in text.upper():
                sqls[cid] = "UNKNOWN"
            else:
                m = re.search(r"(SELECT\b[\s\S]+?)(?:;|\Z)", text, re.I)
                if m:
                    sqls[cid] = normalize_sql(m.group(1))
        else:
            for m in tagged:
                sqls[m.group(1)] = normalize_sql(m.group(2))
    return seals, sqls


def score(tag: str, only: list[str] | None = None) -> dict:
    H = json.loads((RESULTS / "pending_binders_harness.json").read_text())
    seals, sqls = parse_replies(tag)
    rows = []
    want = set(only) if only else None
    for c in H["cases"]:
        if want and c["arm"] not in want:
            continue
        pred, kind = "MISSING", "missing"
        if c["arm"] in ("SQL_EQ", "SQL_NS"):
            sql = normalize_sql(sqls.get(c["id"], ""))
            if not sql:
                pred, kind = "MISSING", "missing"
            elif sql.upper() == "UNKNOWN" or sql.upper().startswith("UNKNOWN "):
                pred, kind = "UNKNOWN", "unknown"
            else:
                try:
                    got = exec_sql(repo_abs(c["db"]), sql)
                    val = got[0][0] if got and got[0][0] is not None else None
                    pred = str(val) if val is not None else "EMPTY"
                    if val == c["gold"]:
                        kind = "gold"
                    elif val == c.get("trap"):
                        kind = "trap"
                    else:
                        kind = "other"
                except Exception:
                    pred, kind = sql[:80], "sql_error"
        else:
            pred = seals.get(c["id"], "MISSING")
            if pred == c["gold"]:
                kind = "gold"
            elif pred.upper() == "UNKNOWN":
                kind = "unknown"
            elif pred == c.get("trap"):
                kind = "trap"
            elif pred == "MISSING":
                kind = "missing"
            else:
                kind = "other"
        rows.append({**{k: v for k, v in c.items() if k not in ("path", "gold_sql")}, "pred": pred, "kind": kind})

    summary = {}
    arms_iter = only or list(H["arms"])
    for arm in arms_iter:
        rs = [r for r in rows if r["arm"] == arm]
        n = len(rs)
        gold = sum(r["kind"] == "gold" for r in rs)
        trap = sum(r["kind"] == "trap" for r in rs)
        unk = sum(r["kind"] == "unknown" for r in rs)
        summary[arm] = {
            "gold": f"{gold}/{n}",
            "trap": trap,
            "unknown": unk,
            "other": n - gold - trap - unk,
            "wilson": wilson(gold, n) if n else None,
        }
    out = RESULTS / f"pending_binders_{tag}.json"
    out.write_text(json.dumps({"tag": tag, "summary": summary, "rows": rows}, indent=2))
    print(json.dumps({"tag": tag, "summary": summary}, indent=2))
    return summary


def run_openai(tag: str = "gpt56", only: list[str] | None = None) -> None:
    from openai import OpenAI

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY")
    model = os.environ.get("OIR_MODEL", "gpt-5.6-sol")
    H = json.loads((RESULTS / "pending_binders_harness.json").read_text())
    client = OpenAI()
    reply_root = RESULTS / f"pending_binders_harness_replies_{tag}"
    kwargs: dict = {"model": model, "messages": []}
    if model.startswith(("gpt-5", "o3", "o4")):
        kwargs["max_completion_tokens"] = 512
    else:
        kwargs["temperature"] = 0
        kwargs["max_tokens"] = 256

    def complete(prompt: str) -> str:
        last = None
        for attempt in range(6):
            try:
                r = client.chat.completions.create(
                    **{**kwargs, "messages": [{"role": "user", "content": prompt}]}
                )
                return (r.choices[0].message.content or "").strip()
            except Exception as e:
                last = e
                time.sleep(min(90.0, 1.8**attempt))
        raise RuntimeError(last)

    for arm, meta in H["arms"].items():
        if only and arm not in only:
            continue
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        sealed = bool(meta.get("sealed_answer"))
        for i, p in enumerate(meta["item_paths"]):
            out = out_dir / f"item_{i}.txt"
            if out.exists() and "ERROR:" not in out.read_text():
                print(f"skip {arm} {i}", flush=True)
                continue
            cid = meta["ids"][i]
            t0 = time.time()
            try:
                raw = complete(repo_abs(p).read_text())
            except Exception as e:
                raw = f"ERROR: {e}"
            if sealed:
                ms = list(SEAL.finditer(raw))
                pred = ms[-1].group(2).strip() if ms else "UNKNOWN"
                text = f"ANSWER_SEALED[{cid}]: {pred}\n# raw_tail\n{raw[-1200:]}\n"
            else:
                ms = list(SQL_RX.finditer(raw))
                if ms:
                    sql = re.sub(r"\s+", " ", ms[-1].group(2)).strip()
                    text = f"SQL[{cid}]: {sql}\n# raw_tail\n{raw[-1200:]}\n"
                    pred = "SQL"
                elif re.search(r"\bUNKNOWN\b", raw, re.I):
                    text = f"SQL[{cid}]: UNKNOWN\n# raw\n{raw[:1500]}\n"
                    pred = "UNKNOWN"
                else:
                    m = re.search(r"(SELECT\b[\s\S]+?)(?:;|\Z)", raw, re.I)
                    sql = re.sub(r"\s+", " ", m.group(1)).strip() if m else "UNKNOWN"
                    text = f"SQL[{cid}]: {sql}\n# raw\n{raw[:1500]}\n"
                    pred = sql[:40]
            if raw.startswith("ERROR:"):
                text = f"ERROR: {raw}\n"
            out.write_text(text)
            print(f"{arm} item_{i} {time.time() - t0:.1f}s -> {pred}", flush=True)
    print("done", model, tag)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build()
    elif cmd == "run":
        tag = sys.argv[2] if len(sys.argv) > 2 else "gpt56"
        only = sys.argv[3:] or None
        run_openai(tag, only)
    elif cmd == "score":
        tag = sys.argv[2] if len(sys.argv) > 2 else "gpt56"
        only = sys.argv[3:] or None
        score(tag, only)
    else:
        raise SystemExit("usage: pending_binders.py build | run [tag] [arm...] | score [tag] [arm...]")


if __name__ == "__main__":
    main()
