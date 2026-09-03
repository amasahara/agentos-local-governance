"""
v0.30.0 release activation checks for Context Authority & Untrusted Provenance.
"""
from __future__ import annotations

import json
from pathlib import Path

from agentos import __version__
from agentos.enforcement_attestation import attest_enforcement
from agentos.policy import load_policy
from agentos.schema_version import CURRENT_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_v0300_release_identity_and_policy() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.30.0"
    assert __version__ == "0.30.0"
    assert CURRENT_SCHEMA_VERSION == 63
    policy = load_policy(ROOT)
    assert policy["version"] == "0.30.0"
    assert policy["documentation_policy"]["current_schema"] == 63
    assert policy["documentation_policy"]["current_release_name"] == "Context Authority & Untrusted Provenance"
    context = policy["context_authority_policy"]
    assert context["enabled"] is True
    assert context["database_schema"] == 63
    assert context["classification_basis"] == "source_origin_only"
    assert context["mcp_mutation_allowed"] is False


def test_v0300_distribution_metadata() -> None:
    metadata = json.loads(
        (ROOT / ".agents/distribution/metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["agentos_version"] == "0.30.0"
    assert metadata["schema_version"] == 63


def test_v0300_required_docs() -> None:
    release_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    node_doc = (
        ROOT / ".agents/docs/CONTEXT_AUTHORITY_UNTRUSTED_PROVENANCE_V0300.md"
    ).read_text(encoding="utf-8")
    for text in (release_notes, node_doc):
        assert "v0.30.0" in text
        assert "Context Authority & Untrusted Provenance" in text
    assert "prompt injection" in release_notes.lower()


def test_v0300_attestation_is_bounded_and_green() -> None:
    report = attest_enforcement(ROOT)
    assert report["ok"] is True, report["findings"]
    context = report["context_authority"]
    for key in (
        "structurally_attested",
        "origin_classification",
        "authority_promotion_forbidden",
        "hash_only_persistence",
        "transport_pinned",
        "cli_read_only",
        "mcp_read_only",
        "broad_nonclaims_preserved",
    ):
        assert context[key] is True
