# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit result identities take precedence over fallback type guesses in tool audits."""

from datakeel.core.models import AssetRef
from datakeel.ontology.tool_refs import reconcile_refs


def test_refs_when_catalog_identity_known_discards_fallback_dataset() -> None:
    """An impact parameter or answer lineage ID must not invent a same-ID dataset."""
    actual = AssetRef(asset_type="metric", asset_id="revenue", version="2")
    result = reconcile_refs([actual], [AssetRef(asset_id="revenue"), actual])
    assert result == [actual]


def test_refs_when_dataset_explicit_preserves_namespace_and_version() -> None:
    """Keep genuine same-ID assets of different types, namespaces, and versions distinct."""
    actual = [AssetRef(asset_type="metric", asset_id="shared"), AssetRef(asset_id="shared")]
    peer = AssetRef(asset_id="shared", namespace="peer")
    assert reconcile_refs(actual, [peer]) == [*actual, peer]
    assert reconcile_refs([], [peer]) == [peer]
