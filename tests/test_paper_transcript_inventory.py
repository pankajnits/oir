"""Paper-cited isolation replies: transcript vs answer-only vs induce.

Locks the provenance inventory so a new answer-only cell cannot appear
silently, and so the documented thin cells cannot vanish without a test update.
"""
from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

spec = importlib.util.spec_from_file_location("reply_parse", ROOT / "harness" / "reply_parse.py")
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)

# Majority kind per (reply_tree, arm) for three-family paper cells.
ANSWER_ONLY = {
    ("entity_rel_2x2_iso_harness_replies_composer25", "OO_UNIQUE"),
    ("entity_rel_2x2_iso_harness_replies_composer25", "OO_AMBIG"),
    ("ceiling_n32_iso_replies_composer25", "PLAIN_PROG"),
    ("ceiling_n32_iso_replies_composer25", "SEAL_NL"),
    ("ceiling_n32_iso_replies_composer25", "SEAL_PROG"),
    ("ceiling_n32_iso_replies_grok45", "PLAIN_PROG"),
    ("ceiling_n32_iso_replies_grok45", "SEAL_NL"),
    ("ceiling_n32_iso_replies_grok45", "SEAL_PROG"),
    ("adv_n32_iso_replies_composer25", "PATH_TRAP"),
    ("adv_n32_iso_replies_composer25", "SAME_TRAP"),
    ("adv_n32_iso_replies_grok45", "PATH_TRAP"),
    ("adv_n32_iso_replies_composer25ff", "CROSS_BALANCED"),
    ("adv_n32_iso_replies_composer25ff", "CROSS_TRAP"),
    ("adv_n32_iso_replies_composer25ff", "PATH_TRAP"),
    ("adv_n32_iso_replies_composer25ff", "SAME_BALANCED"),
    ("adv_n32_iso_replies_composer25ff", "SAME_TRAP"),
    ("adv_n32_iso_replies_grok45ff", "CROSS_BALANCED"),
    ("adv_n32_iso_replies_grok45ff", "CROSS_TRAP"),
    ("adv_n32_iso_replies_grok45ff", "PATH_TRAP"),
    ("adv_n32_iso_replies_grok45ff", "SAME_BALANCED"),
    ("adv_n32_iso_replies_grok45ff", "SAME_TRAP"),
}
INDUCE = {
    ("adv_n32_iso_replies_composer25", "CROSS_BALANCED"),
    ("adv_n32_iso_replies_composer25", "CROSS_TRAP"),
    ("adv_n32_iso_replies_composer25", "SAME_BALANCED"),
    ("adv_n32_iso_replies_grok45", "CROSS_BALANCED"),
    ("adv_n32_iso_replies_grok45", "CROSS_TRAP"),
    ("adv_n32_iso_replies_grok45", "SAME_BALANCED"),
    ("adv_n32_iso_replies_grok45", "SAME_TRAP"),
}
SHORT_TAIL = {
    ("entity_rel_2x2_iso_harness_replies_grok45", "OO_UNIQUE"),
    ("entity_rel_2x2_iso_harness_replies_grok45", "OO_AMBIG"),
}
KNOWN = ANSWER_ONLY | INDUCE | SHORT_TAIL

TREES = [
    "factorial_2x2_iso_harness_replies_gpt56",
    "factorial_2x2_iso_harness_replies_composer25",
    "factorial_2x2_iso_harness_replies_grok45",
    "entity_rel_2x2_iso_harness_replies_gpt56",
    "entity_rel_2x2_iso_harness_replies_composer25",
    "entity_rel_2x2_iso_harness_replies_grok45",
    "ceiling_n32_iso_replies_gpt56",
    "ceiling_n32_iso_replies_composer25",
    "ceiling_n32_iso_replies_grok45",
    "adv_n32_iso_replies_gpt56",
    "adv_n32_iso_replies_composer25",
    "adv_n32_iso_replies_grok45",
    "adv_n32_iso_replies_composer25ff",
    "adv_n32_iso_replies_grok45ff",
    "header_decoy_ablation_iso_harness_replies_gpt56abl",
    "header_decoy_ablation_iso_harness_replies_composer25abl",
    "header_decoy_ablation_iso_harness_replies_grok45abl",
]


def _majority(arm_dir: Path) -> str:
    files = sorted(arm_dir.glob("item_*.txt"))
    assert files, arm_dir
    kinds = Counter(rp.transcript_kind(p.read_text()) for p in files)
    kind, n = kinds.most_common(1)[0]
    assert n == len(files), (arm_dir, dict(kinds))
    return kind


def test_paper_cited_reply_transcript_inventory():
    found_non_transcript = set()
    for tree in TREES:
        root = RESULTS / tree
        assert root.is_dir(), tree
        for arm in sorted(p for p in root.iterdir() if p.is_dir()):
            kind = _majority(arm)
            key = (tree, arm.name)
            if kind == "transcript":
                assert key not in KNOWN, key
            else:
                found_non_transcript.add(key)
                expect = (
                    "answer_only" if key in ANSWER_ONLY else
                    "induce" if key in INDUCE else
                    "short_tail" if key in SHORT_TAIL else
                    None
                )
                assert expect == kind, (key, kind, expect)
    assert found_non_transcript == KNOWN
