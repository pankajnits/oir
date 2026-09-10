#!/usr/bin/env python3
"""Non-LLM baselines for frozen OIR bench: BM25, SealRouter, sqlite ENGINE.

Deterministic. No language-model calls.
"""
from __future__ import annotations

import json
import math
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal, SealRouter

sys.path.insert(0, str(ROOT / "harness"))
from wilson_cis import wilson

RESULTS = ROOT / "results"
SP_DB = ROOT / "data" / "spider" / "spider_data" / "database"
KEY_WIKI = b"oir-wiki-cf-n200-v1"
KEY_SP = b"oir-spider-oir-v1"


def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(s).lower().replace("_", " "))


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.toks = [tokenize(d) for d in docs]
        self.N = max(1, len(self.toks))
        self.avgdl = sum(len(d) for d in self.toks) / self.N
        df: Counter[str] = Counter()
        for d in self.toks:
            df.update(set(d))
        self.idf = {t: math.log((self.N - f + 0.5) / (f + 0.5) + 1.0) for t, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for d in self.toks:
            tf = Counter(d)
            dl = max(1, len(d))
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = self.idf.get(t, 0.0)
                s += idf * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out

    def top_i(self, query: str) -> int:
        sc = self.scores(query)
        if not sc:
            return -1
        return max(range(len(sc)), key=lambda i: (sc[i], -i))


def wiki_cf_baselines():
    H = json.loads((ROOT / "data" / "wiki_cf_n200.json").read_text())
    sealer = EntitySeal(KEY_WIKI)
    n = H["n"]
    bm25_plain = bm25_seal = router = wiki_leak = 0
    for c in H["cases"]:
        edges = [tuple(e) for e in c["edges"]]
        # candidate 2-hop tails: walk every start/rel1 then rel2 — also score each edge as a doc
        docs, tails = [], []
        for h, r, t in edges:
            docs.append(f"{h} {r} {t}")
            tails.append(t)
        # also concatenate gold-shaped paths from start via each first hop
        start = c["start"]
        r1, r2 = c["rels"]
        mids = [t for h, r, t in edges if h == start]
        for mid in mids:
            hops2 = [t for h, r, t in edges if h == mid]
            for tail in hops2:
                docs.append(f"{start} {r1} {mid} {r2} {tail}")
                tails.append(tail)
        i = BM25(docs).top_i(c["question"])
        pred = tails[i]
        if pred == c["cf_gold"]:
            bm25_plain += 1
        if pred == c["wiki_answer"]:
            wiki_leak += 1

        sdocs, stails = [], []
        for h, r, t in edges:
            sh, sr, st = sealer.triple(h, r, t)
            sdocs.append(f"{sh} {sr} {st}")
            stails.append(st)
        j = BM25(sdocs).top_i(c["question"])
        if stails[j] == c["expect_seal"]:
            bm25_seal += 1

        outs = SealRouter([sealer.triple(*e) for e in edges]).path(c["start_seal"], c["rel_seals"])
        if list(dict.fromkeys(outs)) == [c["expect_seal"]]:
            router += 1

    return {
        "n": n,
        "BM25_PLAIN": {"score": f"{bm25_plain}/{n}", "wilson": wilson(bm25_plain, n), "wiki_leak": f"{wiki_leak}/{n}"},
        "BM25_SEAL": {"score": f"{bm25_seal}/{n}", "wilson": wilson(bm25_seal, n)},
        "SEALROUTER": {"score": f"{router}/{n}", "wilson": wilson(router, n)},
        "note": "BM25_PLAIN may use English relation unigrams; BM25_SEAL is lexical IR over HMAC (expected floor).",
    }


def dump_tables(db_id: str):
    db = SP_DB / db_id / f"{db_id}.sqlite"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        if t.startswith("sqlite"):
            continue
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
        rows = [[("" if v is None else str(v)) for v in r] for r in con.execute(f'SELECT * FROM "{t}"')]
        out[t] = (cols, rows)
    con.close()
    return out


def is_numeric_text(v: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", str(v).strip()))


def cell_strings(tables) -> set[str]:
    """Name-like cells only (not digit-only TEXT years/ids)."""
    s: set[str] = set()
    for _, (_cols, rows) in tables.items():
        for row in rows:
            for c in row:
                if c and not is_numeric_text(c):
                    s.add(c)
                    s.add(c.strip())
    return s


def seal_sql_literals(sql: str, sealer: EntitySeal, cells: set[str]) -> str:
    cmap = {c.lower(): c for c in cells}

    def repl(m: re.Match) -> str:
        q, body = m.group(1), m.group(2)
        key = cmap.get(body.lower())
        if key is not None:
            return q + sealer.atom(key) + q
        if body in cells:
            return q + sealer.atom(body) + q
        return m.group(0)

    return re.sub(r"(['\"])([^'\"]*)\1", repl, sql)


def make_sealed_db(db_id: str, sealer: EntitySeal) -> sqlite3.Connection:
    src = SP_DB / db_id / f"{db_id}.sqlite"
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    con = sqlite3.connect(":memory:")
    for (sql,) in src_con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite%'"
    ):
        con.execute(sql)
    for (t,) in src_con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"):
        info = list(src_con.execute(f'PRAGMA table_info("{t}")'))
        rows = list(src_con.execute(f'SELECT * FROM "{t}"'))
        ph = ",".join("?" * len(info))
        sealed = []
        for row in rows:
            new = []
            for v in row:
                if v is None:
                    new.append(None)
                elif isinstance(v, bool):
                    new.append(v)
                elif isinstance(v, (int, float)):
                    new.append(v)
                elif is_numeric_text(str(v)):
                    s = str(v).strip()
                    new.append(int(s) if "." not in s else float(s))
                else:
                    new.append(sealer.atom(str(v)))
            sealed.append(new)
        if sealed:
            con.executemany(f'INSERT INTO "{t}" VALUES ({ph})', sealed)
    src_con.close()
    return con


def nnum(s: str) -> str:
    s = str(s).strip().rstrip(".")
    try:
        f = float(s.replace(",", ""))
        if abs(f - round(f)) < 1e-6:
            return str(int(round(f)))
        return f"{f:.4f}".rstrip("0").rstrip(".")
    except Exception:
        return re.sub(r"\s+", " ", s).lower()


def spider_baselines():
    H = json.loads((ROOT / "data" / "spider_oir_n200.json").read_text())
    sealer = EntitySeal(KEY_SP)
    n = H["n"]
    engine = bm25 = orig = schema = 0
    fails = []
    for it in H["items"]:
        db_id, sql, q, gold = it["db_id"], it["query"], it["question"], it["gold"]
        db = SP_DB / db_id / f"{db_id}.sqlite"
        gold_val = gold
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = con.execute(sql).fetchall()
            if len(row) == 1 and len(row[0]) == 1 and nnum(row[0][0]) == nnum(gold):
                orig += 1
                gold_val = row[0][0]
        except Exception:
            pass
        con.close()

        tables = dump_tables(db_id)
        cells = cell_strings(tables)
        sql_s = seal_sql_literals(sql, sealer, cells)
        if isinstance(gold_val, (int, float)) and not isinstance(gold_val, bool):
            expect = gold_val
        elif is_numeric_text(str(gold_val)):
            expect = str(gold_val).strip()
        else:
            expect = sealer.atom(str(gold_val))
        scon = make_sealed_db(db_id, sealer)
        try:
            got = scon.execute(sql_s).fetchall()
            if len(got) == 1 and len(got[0]) == 1 and nnum(got[0][0]) == nnum(expect):
                engine += 1
            else:
                fails.append({"db": db_id, "q": q[:80], "sql_s": sql_s[:120], "got": str(got)[:80], "expect": expect})
        except Exception as e:
            fails.append({"db": db_id, "q": q[:80], "err": str(e)[:120], "sql_s": sql_s[:160]})
        scon.close()

        docs, vals = [], []
        for tname, (cols, rows) in tables.items():
            for row in rows:
                docs.append(tname + " " + " ".join(f"{c}={v}" for c, v in zip(cols, row)))
                vals.append(row)
        if not docs:
            continue
        i = BM25(docs).top_i(q)
        row = vals[i]
        # pick the cell with highest token overlap with the question among row cells; fallback first text cell
        best, best_s = None, -1.0
        qtok = set(tokenize(q))
        for v in row:
            s = len(qtok & set(tokenize(v)))
            if s > best_s:
                best, best_s = v, s
        if nnum(best) == nnum(gold):
            bm25 += 1

        # schema-link: cell string from the question → prefer a name-like cell on that row
        qlow = q.lower()
        hit_row = None
        hit_cols = None
        for tname, (cols, rows) in tables.items():
            for row in rows:
                for v in row:
                    if v and len(str(v)) >= 3 and str(v).lower() in qlow:
                        hit_row, hit_cols = row, cols
                        break
                if hit_row is not None:
                    break
            if hit_row is not None:
                break
        if hit_row is not None:
            name_i = next((i for i, c in enumerate(hit_cols) if c.lower() in {"name", "title", "bname", "city", "cname"}), 0)
            sl = hit_row[name_i]
            if nnum(sl) == nnum(gold) or any(nnum(v) == nnum(gold) for v in hit_row):
                schema += 1

    return {
        "n": n,
        "SQLITE_ORIG": {"score": f"{orig}/{n}", "wilson": wilson(orig, n)},
        "ENGINE_GOLD": {"score": f"{engine}/{n}", "wilson": wilson(engine, n)},
        "BM25_ROW": {"score": f"{bm25}/{n}", "wilson": wilson(bm25, n)},
        "SCHEMA_LINK": {"score": f"{schema}/{n}", "wilson": wilson(schema, n)},
        "engine_fail_n": len(fails),
        "engine_fail_head": fails[:8],
        "note": "ENGINE_GOLD = gold SQL, names sealed, digit-only TEXT left numeric. SCHEMA_LINK = cell mention in Q. Not CodeS.",
    }


def mcnemar(a_ok: list[bool], b_ok: list[bool]) -> dict:
    """Exact binomial McNemar on discordant pairs (b vs a)."""
    n01 = n10 = 0
    for x, y in zip(a_ok, b_ok):
        if (not x) and y:
            n01 += 1
        elif x and (not y):
            n10 += 1
    n = n01 + n10
    # two-sided exact: 2 * Binomial(n, 0.5).cdf(min)
    if n == 0:
        p = 1.0
    else:
        k = min(n01, n10)
        # P(X<=k) * 2 with X~Bin(n,0.5); cap at 1
        p = 0.0
        for i in range(k + 1):
            p += math.comb(n, i)
        p = min(1.0, 2.0 * p / (2**n))
    return {"n01_b_only": n01, "n10_a_only": n10, "discordant": n, "p_two_sided": round(p, 6)}


def mcnemar_locked():
    """Paired tests on existing MUT JSON (n=12 pilots)."""
    out = {}
    pairs = [
        ("wiki_cf_auto.json", "PLAIN_NL", "SPAN_NL"),
        ("wiki_cf_auto.json", "SPAN_NL", "SEAL_PROG"),
        ("wiki_cf_opaque_rel_auto.json", "SPAN_NL", "LEGEND_NL"),
        ("wiki_cf_opaque_rel_auto.json", "SPAN_NL", "SEAL_PROG"),
        ("spider_oir_auto.json", "PLAIN_NL", "MILD_NL"),
        ("spider_oir_auto.json", "PLAIN_NL", "GOLD_SQL"),
        ("spider_oir_auto.json", "MILD_NL", "MODEL_SQL"),
        ("realqa_2x2_gpt56.json", None, None),
    ]
    # wiki / spider have rows with arm field
    for fname, a, b in pairs:
        path = RESULTS / fname
        if not path.exists() or a is None:
            continue
        d = json.loads(path.read_text())
        by = {}
        for r in d["rows"]:
            by.setdefault(r["arm"], []).append(bool(r["ok"]))
        if a in by and b in by and len(by[a]) == len(by[b]):
            out[f"{fname}:{a} vs {b}"] = mcnemar(by[a], by[b])
    return out


def main():
    wiki = wiki_cf_baselines()
    stats = mcnemar_locked()
    if not SP_DB.exists():
        blob = {
            "wiki_cf_n200": wiki,
            "spider_n200": None,
            "mcnemar_pilots": stats,
            "note": (
                "data/spider sqlite dump is not in this clone; ENGINE 191/200 stays "
                "locked in results/oir_bench_baselines.json. See data/README.md."
            ),
        }
        print(json.dumps(blob, indent=2))
        print("skipped Spider ENGINE (no data/spider); did not overwrite results/oir_bench_baselines.json")
        return
    spider = spider_baselines()
    blob = {"wiki_cf_n200": wiki, "spider_n200": spider, "mcnemar_pilots": stats}
    out = RESULTS / "oir_bench_baselines.json"
    out.write_text(json.dumps(blob, indent=2))
    print(json.dumps(blob, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
