# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable invocation spans survive interruption and retain attributed assets."""

import pytest

from datakeel.core.errors import NotFoundError
from datakeel.core.models import AssetRef
from datakeel.ontology.tool_models import ToolCallContext, ToolInvocationStart, ToolOutcome
from datakeel.storage.database import Database
from datakeel.storage.tool_invocations import begin_invocation, finish_invocation, list_invocations


def test_tool_start_when_dispatch_interrupts_retains_running_record(db: Database) -> None:
    """Keep the attempted invocation even when no completion follows."""
    request = ToolInvocationStart(
        name="search_files",
        arguments_digest="frozen-parameter-digest",
        argument_keys=["dataset_id"],
        context=ToolCallContext(agent_id="demo", session_id="one"),
        asset_refs=[AssetRef(asset_id="generated-dataset")],
    )
    identifier = begin_invocation(db, request)
    db.engine.dispose()
    records = list_invocations(db, "one")
    assert len(records) == 1
    assert records[0].id == identifier
    assert records[0].status == "RUNNING"
    assert records[0].asset_refs == request.asset_refs
    assert records[0].arguments_digest == request.arguments_digest
    assert list_invocations(db, "other") == []


def test_tool_finish_when_failed_retains_error_timing_and_caller(db: Database) -> None:
    """Record one observed failed outcome without losing its asset attribution."""
    refs = [AssetRef(asset_type="file", asset_id="generated-file", version="original")]
    identifier = begin_invocation(
        db,
        ToolInvocationStart(
            name="quarantine_files",
            arguments_digest="digest",
            argument_keys=["selection"],
            context=ToolCallContext(agent_id="demo", session_id="one"),
            asset_refs=refs,
        ),
    )
    finish_invocation(
        db,
        ToolOutcome(
            name="quarantine_files",
            status="FAILED",
            asset_refs=refs,
            error="Selection is stale",
            invocation_id=identifier,
        ),
        1.25,
    )
    record = list_invocations(db)[0]
    assert (record.status, record.error, record.elapsed_ms) == (
        "FAILED",
        "Selection is stale",
        1.25,
    )
    assert record.completed_at is not None
    assert record.completed_at >= record.started_at
    assert (record.actor, record.agent_id, record.session_id) == ("local", "demo", "one")


def test_tool_finish_when_start_missing_rejects_fabricated_span(db: Database) -> None:
    """Do not fabricate completed records for invocations that never started."""
    with pytest.raises(NotFoundError, match="not started"):
        finish_invocation(
            db,
            ToolOutcome(name="list_datasets", status="SUCCEEDED", invocation_id="absent"),
            0,
        )
