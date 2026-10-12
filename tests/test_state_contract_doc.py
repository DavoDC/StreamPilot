"""docs/References/state-contract.md must name every field /status.json serves (the doc cannot drift from fixtures)."""

import os

import fixtures
import health

DOC = os.path.join(os.path.dirname(__file__), "..", "docs", "References", "state-contract.md")


def _doc():
    with open(DOC, encoding="utf-8") as f:
        return f.read()


def test_doc_names_every_field_the_fixtures_emit():
    doc = _doc()
    for name in fixtures.SCENARIOS:
        for field in fixtures.status(name, 1000.0):
            assert f"`{field}`" in doc, f"{field} missing from state-contract.md"


def test_doc_names_the_contract_fields_and_the_stale_rule():
    doc = _doc()
    for field in ("schema", "generated_at", "stale"):
        assert f"`{field}`" in doc
    assert "max(poll_interval * 4, 8)" in doc
