"""Adapters used by harness/prove_layer — no Excel, no Spider dump."""
from __future__ import annotations

from oir.adapters import GraphDataset, ceo_hq_edges


def test_ceo_hq_graph_from_inline_records():
    g = GraphDataset(
        [{"person": "Ada", "company": "Acme", "hq": "Dallas"}],
        ceo_hq_edges,
        id_key="person",
    )
    triples = g.triples_for(g.records[0])
    assert any(t[1] == "works_at" for t in triples)
    assert any(t[2] == "Dallas" for t in triples)
