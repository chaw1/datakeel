# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence source authorization cannot expand the existing selected-sample contract."""

from pathlib import Path

import pytest

from datakeel.core.data_asset_models import AssetUsageQuery
from datakeel.core.errors import AuthorizationError
from datakeel.core.evidence_models import EvidenceAnchor
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.evidence.query_models import EvidenceQueryResult, EvidenceSample
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_rows import AssertionRow
from tests.assets.entry_helpers import grant, publish
from tests.evidence.interface_fixtures import seed_query_evidence


def test_evidence_tool_keeps_selection_separate_from_all_disclosed_source_refs(
    db: Database, tmp_path: Path
) -> None:
    """Inner results select displayed samples; outer tool audit retains all sidecar sources."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    arguments = JsonDocument({"dataset_id": dataset, "split": "val", "page_size": 2})
    result = invoke_function(db, "query_evidence", arguments)
    page = EvidenceQueryResult.model_validate(result.data)
    selected = [item.asset_ref for item in page.items]
    anchors = [
        anchor.asset_ref
        for item in page.items
        for assertion in item.assertions
        for anchor in assertion.anchors
    ]
    assert any(ref not in selected for ref in anchors)
    assert result.asset_refs == selected
    tool = invoke_tool(db, "query_evidence", arguments, ToolCallContext())
    assert tool.status == "SUCCEEDED", tool.error
    assert FunctionResult.model_validate(tool.content.root).asset_refs == selected
    assert all(ref in tool.asset_refs for ref in anchors)
    for name in ("get_evidence", "explain_sample"):
        detail = invoke_function(db, name, JsonDocument({"asset_id": selected[0].asset_id}))
        assert detail.asset_refs == [selected[0]]


def test_external_anchor_policy_is_enforced_without_adding_it_to_selection(
    db: Database, tmp_path: Path
) -> None:
    """A displayed sample needs authorization for an independently protected source anchor."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    selected = invoke_function(
        db, "query_evidence", JsonDocument({"dataset_id": dataset, "page_size": 1})
    )
    sample = EvidenceQueryResult.model_validate(selected.data).items[0]
    path = tmp_path / "cross-source.txt"
    path.write_text("Generated external source", encoding="utf-8")
    external = import_paths(db, "External source", [path])
    version, files = source_manifest(db, external.id)
    anchor_ref = AssetRef(asset_type="file", asset_id=files[0].id, version=version)
    assertion = sample.assertions[0].model_copy(
        update={
            "id": "cross-source-assertion",
            "anchors": (EvidenceAnchor(asset_ref=anchor_ref, content_revision=files[0].sha256),),
        }
    )
    with db.session() as session:
        session.add(
            AssertionRow(
                id=assertion.id,
                subject_id=assertion.subject.asset_id,
                predicate=assertion.predicate,
                producer_event_id=assertion.producer_event_id,
                payload=assertion.model_dump(mode="json"),
            )
        )
        session.commit()
    asset = publish(db, AssetRef(asset_id=external.id))
    arguments = JsonDocument({"asset_id": sample.asset_ref.asset_id})
    with pytest.raises(AuthorizationError, match="apply for access"):
        invoke_function(db, "get_evidence", arguments)
    assert list_usage(db, AssetUsageQuery(asset_id=asset.id)) == ()
    grant(db, asset, "valid", "query")
    outcome = invoke_tool(db, "get_evidence", arguments, ToolCallContext())
    assert outcome.status == "SUCCEEDED", outcome.error
    result = FunctionResult.model_validate(outcome.content.root)
    assert result.asset_refs == [sample.asset_ref]
    assert any(
        anchor_ref == anchor.asset_ref
        for assertion in EvidenceSample.model_validate(result.data).assertions
        for anchor in assertion.anchors
    )
    assert anchor_ref in outcome.asset_refs
    assert len(list_usage(db, AssetUsageQuery(asset_id=asset.id))) == 1
