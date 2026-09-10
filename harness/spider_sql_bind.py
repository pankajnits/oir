#!/usr/bin/env python3
"""Spider public-data bind: same-σ overlap vs SQLCOL: namespace.

Spider train+dev items from data/spider_oir_n200.json (CC-BY-SA-4.0).
Slice A: a table/column identifier appears in q. Slice B: it does not.
EQ: HMAC(name) in q equals the sqlite identifier. NS: HMAC(SQLCOL:name) does not.
No local schema linker. No rewritten template questions. We execute sealed SQL.

Not a Spider leaderboard. Not MaskSQL. Not the Wikidata 2×2.
Seed 20260903. OpenAI n=100 (A) + remaining B.
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

from oir import EntitySeal
from paths import repo_abs, repo_rel
from wilson_cis import wilson

SPIDER_DB = ROOT / "data" / "spider" / "spider_data" / "database"
ITEMS = ROOT / "data" / "spider_oir_n200.json"
RESULTS = ROOT / "results"
RUNS = ROOT / "runs" / "spider_sql_bind"
SEED = 20260903
N_A = 100
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
SQL_RX = re.compile(r"SQL\[([^\]]+)\]:\s*(.+?)(?=\nSQL\[|\nANSWER_|\n#####|\Z)", re.I | re.S)
ATOM = re.compile(r"E[0-9a-f]{12}", re.I)

PROTO = """
PROTOCOL (English; do not decrypt):
- The context is this file only: QUESTION + SCHEMA. There are no data rows.
- Do not use world knowledge. Do not decrypt.
- SCHEMA is bilingual: English name = sealed sqlite table or column.
- A sealed QUESTION token that equals a SCHEMA identifier is that table or column.
- Write ONE sqlite SELECT using the sealed identifiers. We execute it on hidden rows.
- Join tables on sealed names that appear in two tables.
- If no QUESTION token equals a SCHEMA identifier, output UNKNOWN.
""".strip()


def nnum(s) -> str:
    s = str(s).strip().rstrip(".")
    try:
        f = float(str(s).replace(",", ""))
        if abs(f - round(f)) < 1e-6:
            return str(int(round(f)))
        return f"{f:.4f}".rstrip("0").rstrip(".")
    except Exception:
        return re.sub(r"\s+", " ", str(s)).lower()


def qid(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def schema_idents(db_id: str) -> list[str]:
    p = SPIDER_DB / db_id / f"{db_id}.sqlite"
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    out: list[str] = []
    seen: set[str] = set()
    for (t,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
    ):
        if t not in seen:
            out.append(t)
            seen.add(t)
        for c in con.execute(f"PRAGMA table_info({qid(t)})"):
            if c[1] not in seen:
                out.append(c[1])
                seen.add(c[1])
    con.close()
    return out


def ident_keys(ident: str) -> list[str]:
    keys = [ident]
    if "_" in ident:
        keys.append(ident.replace("_", " "))
    for p in ident.split("_"):
        if len(p) >= 4:
            keys.append(p)
    # unique, longest first
    seen, ordered = set(), []
    for k in sorted(keys, key=len, reverse=True):
        lk = k.lower()
        if lk not in seen:
            seen.add(lk)
            ordered.append(k)
    return ordered


def overlap_map(question: str, idents: list[str]) -> dict[str, str]:
    """ident -> which question surface matched (original ident)."""
    ql = question.lower()
    words = {w.lower() for w in WORD.findall(question)}
    hit: dict[str, str] = {}
    for ident in sorted(idents, key=len, reverse=True):
        for k in ident_keys(ident):
            if " " in k:
                if k.lower() in ql:
                    hit[ident] = ident
                    break
            elif k.lower() in words:
                hit[ident] = ident
                break
    return hit


def seal_overlap_question(q: str, fmap: dict[str, str], hit: dict[str, str]) -> str:
    out = q
    for ident in sorted(hit, key=len, reverse=True):
        h = fmap[ident]
        for k in ident_keys(ident):
            out = re.sub(rf"(?i)\b{re.escape(k)}\b", h, out)
    return out


def clone_hmac(src: Path, dst: Path, fmap: dict[str, str]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dst_con = sqlite3.connect(dst)
    tables = [
        t
        for (t,) in src_con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        )
    ]
    for t in tables:
        cols = [c[1] for c in src_con.execute(f"PRAGMA table_info({qid(t)})")]
        types = [c[2] or "TEXT" for c in src_con.execute(f"PRAGMA table_info({qid(t)})")]
        ht, hcols = fmap[t], [fmap[c] for c in cols]
        spec = ", ".join(f"{qid(hc)} {ty}" for hc, ty in zip(hcols, types))
        dst_con.execute(f"CREATE TABLE {qid(ht)} ({spec})")
        rows = src_con.execute(f"SELECT * FROM {qid(t)}").fetchall()
        if rows:
            ph = ",".join("?" * len(cols))
            dst_con.executemany(f"INSERT INTO {qid(ht)} VALUES ({ph})", rows)
    dst_con.commit()
    dst_con.close()
    src_con.close()


def exec_sql(db: Path, sql: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def rewrite_gold_sql(sql: str, fmap: dict[str, str]) -> str:
    out = sql
    for ident in sorted(fmap, key=len, reverse=True):
        out = re.sub(rf"(?i)\b{re.escape(ident)}\b", qid(fmap[ident]), out)
    return out


def schema_block(idents: list[str], fmap: dict[str, str], db_id: str, src: Path) -> str:
    legend = "\n".join(f"{n} = {fmap[n]}" for n in idents)
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    shapes = []
    for (t,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
    ):
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({qid(t)})")]
        shapes.append(f"{t}({', '.join(cols)})")
    con.close()
    return (
        f"DB: {db_id}\n"
        "SCHEMA (English name → sealed sqlite identifier):\n"
        f"{legend}\n\n"
        + "\n".join(shapes)
        + "\n"
    )


def pack(cid: str, schema: str, q: str) -> str:
    return "\n".join(
        [
            "MODEL UNDER TEST. Read ONLY this file. The schema is the context. "
            "No decrypt. No world knowledge. Do not open other files.",
            f"Format: SQL[{cid}]: <sqlite>",
            "If more than one reading is possible, output UNKNOWN.",
            "",
            "Sealed question. Schema maps English names to sealed identifiers. No rows.",
            "",
            f"##### ID {cid} #####",
            schema,
            "QUESTION:",
            q,
            "",
            PROTO,
        ]
    )


def classify(items: list[dict]) -> tuple[list[dict], list[dict]]:
    a, b = [], []
    for it in items:
        idents = schema_idents(it["db_id"])
        hit = overlap_map(it["question"], idents)
        rec = {**it, "idents": idents, "hit": hit}
        (a if hit else b).append(rec)
    return a, b


def build() -> dict:
    if not SPIDER_DB.exists():
        raise SystemExit(
            "Missing data/spider/spider_data/database. "
            "ln -s ../../archive/oir_local/data/spider data/spider"
        )
    raw = json.loads(ITEMS.read_text())["items"]
    a, b = classify(raw)
    rng = random.Random(SEED)
    a_use = rng.sample(a, min(N_A, len(a)))
    use = [("A", x) for x in a_use] + [("B", x) for x in b]

    if RUNS.exists():
        for p in RUNS.rglob("prompt.txt"):
            p.unlink()
        for p in RUNS.rglob("*.sqlite"):
            p.unlink()

    cases = []
    arms = {
        "SQL_EQ": {"ids": [], "item_paths": []},
        "SQL_NS": {"ids": [], "item_paths": []},
    }
    gold_ok = 0
    for i, (slice_, it) in enumerate(use):
        sealer = EntitySeal(rng.randbytes(16))
        fmap_eq = {n: sealer.atom(n) for n in it["idents"]}
        fmap_ns = {n: sealer.atom(f"SQLCOL:{n}") for n in it["idents"]}
        src = SPIDER_DB / it["db_id"] / f"{it['db_id']}.sqlite"
        db_eq = RUNS / "db" / f"eq_{i}.sqlite"
        db_ns = RUNS / "db" / f"ns_{i}.sqlite"
        clone_hmac(src, db_eq, fmap_eq)
        clone_hmac(src, db_ns, fmap_ns)
        gsql_eq = rewrite_gold_sql(it["query"], fmap_eq)
        try:
            got = exec_sql(db_eq, gsql_eq)
            if got and got[0][0] is not None and nnum(got[0][0]) == nnum(it["gold"]):
                gold_ok += 1
        except Exception:
            pass
        q_eq = seal_overlap_question(it["question"], fmap_eq, it["hit"])
        # NS uses the same sealed question (HMAC of the English name, not SQLCOL:)
        assert (ATOM.findall(q_eq) and slice_ == "A") or (not ATOM.findall(q_eq) and slice_ == "B")
        if slice_ == "A":
            assert set(ATOM.findall(q_eq)) & set(fmap_eq.values())
            assert not (set(ATOM.findall(q_eq)) & set(fmap_ns.values()))

        for arm, fmap, dbp in (
            ("SQL_EQ", fmap_eq, db_eq),
            ("SQL_NS", fmap_ns, db_ns),
        ):
            cid = f"PB_{arm}_{i}"
            sch = schema_block(it["idents"], fmap, it["db_id"], src)
            text = pack(f"PB_SQL_{i}", sch, q_eq)
            path = RUNS / arm / f"item_{i}" / "prompt.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            rec = {
                "i": i,
                "id": cid,
                "arm": arm,
                "slice": slice_,
                "db_id": it["db_id"],
                "app_q": it["question"],
                "q_sealed": q_eq,
                "gold": it["gold"],
                "gold_sql": it["query"],
                "path": repo_rel(path),
                "db": repo_rel(dbp),
                "overlap": sorted(it["hit"]),
            }
            cases.append(rec)
            arms[arm]["ids"].append(cid)
            arms[arm]["item_paths"].append(repo_rel(path))

    h = {
        "n_items": len(use),
        "n_A": sum(1 for s, _ in use if s == "A"),
        "n_B": sum(1 for s, _ in use if s == "B"),
        "gold_rewrite_ok": gold_ok,
        "seed": SEED,
        "source": "data/spider_oir_n200.json",
        "license": "CC-BY-SA-4.0 (Spider)",
        "nonclaim": (
            "Public Spider items; not a leaderboard. EQ vs NS is token overlap, "
            "not local schema linking. Specified bilingual schema. Not confidentiality."
        ),
        "arms": arms,
        "cases": cases,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "spider_sql_bind_harness.json"
    out.write_text(json.dumps(h, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {
                "n_items": h["n_items"],
                "n_A": h["n_A"],
                "n_B": h["n_B"],
                "gold_rewrite_ok": gold_ok,
                "out": str(out),
            },
            indent=2,
        )
    )
    return h


def normalize_sql(sql: str) -> str:
    sql = re.sub(r"\s+", " ", sql or "").strip().rstrip(";")
    sql = re.split(r"\s+#", sql, 1)[0].strip()
    return sql


def parse_replies(tag: str) -> dict[str, str]:
    d = RESULTS / f"spider_sql_bind_replies_{tag}"
    sqls: dict[str, str] = {}
    if not d.exists():
        return sqls
    for p in d.rglob("*.txt"):
        if p.parent.name not in ("SQL_EQ", "SQL_NS"):
            continue
        idx = p.stem.split("_")[-1]
        cid = f"PB_{p.parent.name}_{idx}"
        text = p.read_text()
        tagged = list(SQL_RX.finditer(text))
        if tagged:
            sqls[cid] = normalize_sql(tagged[-1].group(2))
        elif re.search(r"\bUNKNOWN\b", text, re.I) and "SELECT" not in text.upper():
            sqls[cid] = "UNKNOWN"
        else:
            m = re.search(r"(SELECT\b[\s\S]+?)(?:;|\Z)", text, re.I)
            if m:
                sqls[cid] = normalize_sql(m.group(1))
    return sqls


def score(tag: str) -> dict:
    H = json.loads((RESULTS / "spider_sql_bind_harness.json").read_text())
    sqls = parse_replies(tag)
    rows = []
    for c in H["cases"]:
        sql = sqls.get(c["id"], "")
        kind = "missing"
        pred = "MISSING"
        if not sql:
            pass
        elif sql.upper() == "UNKNOWN" or sql.upper().startswith("UNKNOWN "):
            pred, kind = "UNKNOWN", "unknown"
        else:
            try:
                got = exec_sql(repo_abs(c["db"]), sql)
                val = got[0][0] if got and got[0][0] is not None else None
                pred = str(val) if val is not None else "EMPTY"
                if val is not None and nnum(val) == nnum(c["gold"]):
                    kind = "gold"
                else:
                    kind = "other"
            except Exception:
                pred, kind = sql[:80], "sql_error"
        rows.append({**{k: v for k, v in c.items() if k != "gold_sql"}, "pred": pred, "kind": kind})

    def bucket(arm: str, slice_: str | None = None):
        rs = [
            r
            for r in rows
            if r["arm"] == arm and (slice_ is None or r["slice"] == slice_)
        ]
        n = len(rs)
        gold = sum(r["kind"] == "gold" for r in rs)
        unk = sum(r["kind"] == "unknown" for r in rs)
        return {
            "gold": f"{gold}/{n}",
            "unknown": unk,
            "other": n - gold - unk,
            "wilson": wilson(gold, n) if n else None,
        }

    summary = {
        "SQL_EQ": bucket("SQL_EQ"),
        "SQL_NS": bucket("SQL_NS"),
        "SQL_EQ_A": bucket("SQL_EQ", "A"),
        "SQL_NS_A": bucket("SQL_NS", "A"),
        "SQL_EQ_B": bucket("SQL_EQ", "B"),
        "SQL_NS_B": bucket("SQL_NS", "B"),
    }
    out = RESULTS / f"spider_sql_bind_{tag}.json"
    out.write_text(json.dumps({"tag": tag, "summary": summary, "rows": rows}, indent=2))
    print(json.dumps({"tag": tag, "summary": summary}, indent=2))
    return summary


def run_openai(tag: str = "gpt56") -> None:
    from openai import OpenAI

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY")
    model = os.environ.get("OIR_MODEL", "gpt-5.6-sol")
    H = json.loads((RESULTS / "spider_sql_bind_harness.json").read_text())
    client = OpenAI()
    reply_root = RESULTS / f"spider_sql_bind_replies_{tag}"
    kwargs: dict = {"model": model, "messages": []}
    if model.startswith(("gpt-5", "o3", "o4")):
        kwargs["max_completion_tokens"] = 700
    else:
        kwargs["temperature"] = 0
        kwargs["max_tokens"] = 400

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
        out_dir = reply_root / arm
        out_dir.mkdir(parents=True, exist_ok=True)
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
            ms = list(SQL_RX.finditer(raw))
            if ms:
                sql = re.sub(r"\s+", " ", ms[-1].group(2)).strip()
                text = f"SQL[{cid}]: {sql}\n# raw_tail\n{raw[-1200:]}\n"
            elif re.search(r"\bUNKNOWN\b", raw, re.I):
                text = f"SQL[{cid}]: UNKNOWN\n# raw\n{raw[:1500]}\n"
            else:
                m = re.search(r"(SELECT\b[\s\S]+?)(?:;|\Z)", raw, re.I)
                sql = re.sub(r"\s+", " ", m.group(1)).strip() if m else "UNKNOWN"
                text = f"SQL[{cid}]: {sql}\n# raw\n{raw[:1500]}\n"
            if raw.startswith("ERROR:"):
                text = f"ERROR: {raw}\n"
            out.write_text(text)
            print(f"{arm} item_{i} {time.time() - t0:.1f}s", flush=True)
    print("done", model, tag)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build()
    elif cmd == "run":
        run_openai(sys.argv[2] if len(sys.argv) > 2 else "gpt56")
    elif cmd == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else "gpt56")
    else:
        raise SystemExit("usage: spider_sql_bind.py build | run [tag] | score [tag]")


if __name__ == "__main__":
    main()
