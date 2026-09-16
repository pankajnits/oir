#!/usr/bin/env python3
"""Build a city-typed Wikidata CEO freeze (n=200) with QIDs a reviewer can check.

Does not touch data/real/wikidata_ceo_hops_v2.json (the n=32 source).

  python3 harness/fetch_wikidata_ceo_n200.py          # SPARQL + freeze
  python3 harness/fetch_wikidata_ceo_n200.py verify   # re-check QIDs live

Each record stores person/company/hq atoms (EntitySeal.normalize) plus Wikidata
QIDs and the HQ P31 class used as the city filter. Gold is P159 of a P169
company, and that P159 node is an instance of a city-like class (not a
station, building, or state).
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oir import EntitySeal  # noqa: E402

OUT = ROOT / "data" / "real" / "wikidata_ceo_hops_n200.json"
META = ROOT / "data" / "real" / "wikidata_ceo_hops_n200.meta.json"
VERIFY = ROOT / "results" / "wikidata_ceo_hops_n200_verify.json"
SEED = 20260915
N = 200
MAX_PER_HQ = 3
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "OIR-n200/1.0 (research freeze; Wikidata Query Service)"

# Positive city-like classes. Stations/buildings/states are excluded below.
CITY_QIDS = (
    "Q515",      # city
    "Q1549591",  # big city
    "Q1093829",  # city of the United States
    "Q1637706",  # city with millions of inhabitants
    "Q3957",     # town
    "Q5119",     # capital city
    "Q13539802", # place with town rights and privileges
    "Q5153359",  # municipality of the Czech Republic
    "Q7930989",  # city/town
    "Q1549591",
)
# Reject these even if also typed as a city.
BAN_QIDS = (
    "Q55488",   # railway station
    "Q41176",   # building
    "Q35657",   # U.S. state
    "Q7275",    # state
    "Q23442",   # island
    "Q23397",   # lake
    "Q3947",    # house
    "Q11303",   # skyscraper
    "Q3518095", # railway building
)


def sparql(query: str, *, retries: int = 6) -> dict:
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(
        ENDPOINT + "?" + params,
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
    )
    last: Exception | None = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            last = e
            time.sleep(min(30.0, 2.0 ** i))
    raise RuntimeError(last)


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def atom(label: str) -> str:
    return re.sub(r"_+", "_", EntitySeal.normalize(label))


def pull_candidates() -> list[dict]:
    values = " ".join(f"wd:{q}" for q in dict.fromkeys(CITY_QIDS))
    bans = "\n  ".join(f"FILTER NOT EXISTS {{ ?hq wdt:P31 wd:{q} }}" for q in BAN_QIDS)
    query = f"""
SELECT DISTINCT ?person ?personLabel ?company ?companyLabel ?hq ?hqLabel ?cityClass ?cityClassLabel
WHERE {{
  ?company wdt:P169 ?person .
  ?company wdt:P159 ?hq .
  VALUES ?cityClass {{ {values} }}
  ?hq wdt:P31 ?cityClass .
  ?person wdt:P31 wd:Q5 .
  {bans}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 4000
"""
    rows = sparql(query)["results"]["bindings"]
    by_key: dict[tuple[str, str, str], dict] = {}
    for b in rows:
        person_q, company_q, hq_q = qid(b["person"]["value"]), qid(b["company"]["value"]), qid(b["hq"]["value"])
        rec = {
            "person": atom(b["personLabel"]["value"]),
            "company": atom(b["companyLabel"]["value"]),
            "hq": atom(b["hqLabel"]["value"]),
            "person_qid": person_q,
            "company_qid": company_q,
            "hq_qid": hq_q,
            "hq_p31": qid(b["cityClass"]["value"]),
            "hq_p31_label": b["cityClassLabel"]["value"],
            "person_label": b["personLabel"]["value"],
            "company_label": b["companyLabel"]["value"],
            "hq_label": b["hqLabel"]["value"],
        }
        if rec["person"].startswith("Q") and rec["person"][1:].isdigit():
            continue
        if rec["company"].startswith("Q") and rec["company"][1:].isdigit():
            continue
        if rec["hq"].startswith("Q") and rec["hq"][1:].isdigit():
            continue
        if min(len(rec["person"]), len(rec["company"]), len(rec["hq"])) < 2:
            continue
        key = (person_q, company_q, hq_q)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = rec
        elif rec["hq_p31"] not in prev.get("hq_p31_all", [prev["hq_p31"]]):
            prev.setdefault("hq_p31_all", [prev["hq_p31"]]).append(rec["hq_p31"])
    return list(by_key.values())


def _norm_collisions(rows: list[dict]) -> None:
    for field, qid_field in (("person", "person_qid"), ("company", "company_qid"), ("hq", "hq_qid")):
        seen: dict[str, str] = {}
        for r in rows:
            prev = seen.get(r[field])
            if prev and prev != r[qid_field]:
                raise ValueError(f"normalize collision on {field}: {r[field]} {prev} vs {r[qid_field]}")
            seen[r[field]] = r[qid_field]


def arrange_cycle(rows: list[dict]) -> list[dict]:
    remaining = list(rows)
    order = [remaining.pop(0)]
    while remaining:
        hq, person = order[-1]["hq"], order[-1]["person"]
        idx = next(
            (i for i, r in enumerate(remaining) if r["hq"] != hq and r["person"] != person),
            None,
        )
        if idx is None:
            raise ValueError("cannot arrange a cyclic decoy order (hq/person clash)")
        order.append(remaining.pop(idx))
    if order[-1]["hq"] == order[0]["hq"] or order[-1]["person"] == order[0]["person"]:
        for i in range(1, len(order) - 1):
            a, b = order[i], order[-1]
            if (
                a["hq"] != order[0]["hq"]
                and a["person"] != order[0]["person"]
                and b["hq"] != order[i - 1]["hq"]
                and b["person"] != order[i - 1]["person"]
                and b["hq"] != order[i + 1]["hq"]
                and b["person"] != order[i + 1]["person"]
                and a["hq"] != order[-2]["hq"]
                and a["person"] != order[-2]["person"]
            ):
                order[i], order[-1] = order[-1], order[i]
                break
        else:
            raise ValueError("cycle close failed: last item shares hq/person with first")
    n = len(order)
    for i, row in enumerate(order):
        nxt = order[(i + 1) % n]
        if nxt["hq"] == row["hq"] or nxt["person"] == row["person"]:
            raise ValueError(f"cyclic decoy clash at {i}: {row['person']} -> {nxt['person']}")
    return order


def sample_n(cands: list[dict], n: int = N) -> list[dict]:
    rng = random.Random(SEED)
    # Unique person, unique company; cap city so one HQ cannot dominate.
    rng.shuffle(cands)
    picked, seen_p, seen_c, hq_n = [], set(), set(), Counter()
    for r in cands:
        if r["person"] in seen_p or r["company"] in seen_c:
            continue
        if hq_n[r["hq"]] >= MAX_PER_HQ:
            continue
        atoms = (r["person"], r["company"], r["hq"], "works_at", "headquartered_in",
                 "partner_of", "located_in")
        try:
            EntitySeal.assert_raw_injective(atoms)
        except ValueError:
            continue
        picked.append(r)
        seen_p.add(r["person"])
        seen_c.add(r["company"])
        hq_n[r["hq"]] += 1
        if len(picked) == n:
            break
    if len(picked) < n:
        raise SystemExit(f"only {len(picked)} city-typed unique CEO rows after filters; need {n}")
    return arrange_cycle(picked)


def verify_batch(records: list[dict], *, batch: int = 40) -> dict:
    missing = []
    checked = 0
    for i in range(0, len(records), batch):
        chunk = records[i : i + batch]
        values = " ".join(
            f"(wd:{r['company_qid']} wd:{r['person_qid']} wd:{r['hq_qid']})" for r in chunk
        )
        query = f"""
SELECT ?company ?person ?hq WHERE {{
  VALUES (?company ?person ?hq) {{ {values} }}
  ?company wdt:P169 ?person .
  ?company wdt:P159 ?hq .
}}
"""
        hit = {
            (qid(b["company"]["value"]), qid(b["person"]["value"]), qid(b["hq"]["value"]))
            for b in sparql(query)["results"]["bindings"]
        }
        for r in chunk:
            key = (r["company_qid"], r["person_qid"], r["hq_qid"])
            checked += 1
            if key not in hit:
                missing.append(key)
        time.sleep(0.4)
    # City class still present
    city_fail = []
    for i in range(0, len(records), batch):
        chunk = records[i : i + batch]
        values = " ".join(f"wd:{r['hq_qid']}" for r in chunk)
        city_vals = " ".join(f"wd:{q}" for q in dict.fromkeys(CITY_QIDS))
        query = f"""
SELECT DISTINCT ?hq WHERE {{
  VALUES ?hq {{ {values} }}
  VALUES ?cls {{ {city_vals} }}
  ?hq wdt:P31 ?cls .
}}
"""
        ok = {qid(b["hq"]["value"]) for b in sparql(query)["results"]["bindings"]}
        for r in chunk:
            if r["hq_qid"] not in ok:
                city_fail.append(r["hq_qid"])
        time.sleep(0.4)
    return {
        "n": len(records),
        "checked": checked,
        "p169_p159_ok": checked - len(missing),
        "p169_p159_missing": missing,
        "city_p31_ok": len(records) - len(city_fail),
        "city_p31_missing": city_fail,
        "utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT,
    }


def freeze() -> list[dict]:
    print("SPARQL pull…", flush=True)
    cands = pull_candidates()
    print(f"candidates {len(cands)} unique (person,company,hq) triples", flush=True)
    picked = sample_n(cands, N)
    _norm_collisions(picked)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(picked, indent=2, ensure_ascii=False) + "\n")
    meta = {
        "n": N,
        "seed": SEED,
        "max_per_hq": MAX_PER_HQ,
        "source": "Wikidata Query Service",
        "endpoint": ENDPOINT,
        "pulled_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": (
            "company P169 person (CEO); company P159 hq; hq P31 city-like class; "
            "person P31 human; exclude station/building/state P31"
        ),
        "city_classes": list(dict.fromkeys(CITY_QIDS)),
        "banned_p31": list(BAN_QIDS),
        "hq_histogram": Counter(r["hq"] for r in picked).most_common(),
        "unique_people": len({r["person"] for r in picked}),
        "unique_companies": len({r["company"] for r in picked}),
        "unique_hq": len({r["hq"] for r in picked}),
        "verify": "python3 harness/fetch_wikidata_ceo_n200.py verify",
    }
    META.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print("wrote", OUT, "n", N, "hq", meta["unique_hq"], flush=True)
    print("verify live SPARQL…", flush=True)
    report = verify_batch(picked)
    VERIFY.parent.mkdir(parents=True, exist_ok=True)
    VERIFY.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: report[k] for k in ("n", "p169_p159_ok", "city_p31_ok", "p169_p159_missing", "city_p31_missing")}, indent=2))
    if report["p169_p159_missing"] or report["city_p31_missing"]:
        raise SystemExit("live Wikidata verify failed; not using this freeze")
    return picked


def main() -> None:
    if sys.argv[1:] == ["verify"]:
        recs = json.loads(OUT.read_text())
        report = verify_batch(recs)
        VERIFY.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(report, indent=2, ensure_ascii=False)[:2000])
        if report["p169_p159_missing"] or report["city_p31_missing"]:
            raise SystemExit("verify failed")
        return
    freeze()


if __name__ == "__main__":
    main()
