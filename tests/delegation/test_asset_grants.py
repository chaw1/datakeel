# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Delegated conclusions retain native source scopes when replayed after revocation."""

from pathlib import Path

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import (
    Conversation,
    ConversationCreate,
    MessageInput,
    ScriptedResponse,
    ToolCall,
)
from datakeel.core.data_asset_models import AssetUsageQuery
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.delegation.models import ChildResult
from datakeel.delegation.service import delegate
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.storage import conversation_store
from datakeel.storage.conversation_asset_refs import conversation_asset_refs
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database
from datakeel.storage.evidence_queries import query_evidence
from tests.assets.entry_helpers import grant, publish, revoke
from tests.delegation.test_execution import request, search
from tests.evidence.interface_fixtures import seed_query_evidence


def _must_not_run(_child: Conversation, _task: str) -> ChildResult:
    msg = "A durable child conclusion must be replayed without executing again"
    raise AssertionError(msg)


def _script(
    call: ScriptedResponse, summary: str, asset_id: str, *, nested: bool
) -> list[ScriptedResponse]:
    steps = [search(), call]
    if nested:
        steps.extend(
            [search("evidence-reviewer"), request("evidence-reviewer", "evidence-reviewer")]
        )
    steps.extend(
        [
            ScriptedResponse(
                agent="evidence-reviewer",
                tool_calls=[
                    ToolCall(
                        name="get_evidence",
                        arguments=JsonDocument({"asset_id": asset_id}),
                    )
                ],
            ),
            ScriptedResponse(agent="evidence-reviewer", content=summary),
        ]
    )
    if nested:
        steps.append(
            ScriptedResponse(agent="evidence-reviewer", content="Nested source conclusion")
        )
    steps.append(ScriptedResponse(agent="main", content="Parent conclusion"))
    return steps


@pytest.mark.parametrize("nested", [False, True])
def test_delegated_data_when_grant_revoked_cannot_replay_old_conclusion(
    db: Database, tmp_path: Path, *, nested: bool
) -> None:
    """Actual descendant reads attach refs; cached direct and nested summaries recheck the grant."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    sample = query_evidence(db, EvidenceQuery(dataset_id=dataset)).items[0]
    asset = publish(db, AssetRef(asset_id=dataset))
    grant_id = grant(db, asset, "valid", "query")
    assert grant_id is not None
    root = create_conversation(db, ConversationCreate(dataset_id=dataset))
    call = request(name="evidence-reviewer")
    steps = _script(
        call, sample.caption or sample.filename, sample.asset_ref.asset_id, nested=nested
    )
    events = list(
        send_message(
            db,
            root.id,
            MessageInput(content="Inspect source evidence"),
            provider=FakeProvider(steps),
        )
    )
    outcome = next(
        event.outcome
        for event in events
        if event.outcome and event.outcome.name == "delegate_agent" and event.agent_path == "main"
    )
    assert outcome.status == "SUCCEEDED"
    child_id = outcome.content.root["conversation_id"]
    assert isinstance(child_id, str)
    assert outcome.asset_refs
    assert set(outcome.asset_refs) == set(conversation_asset_refs(db, child_id))
    before = len(list_usage(db, AssetUsageQuery(asset_id=asset.id)))
    replay = delegate(db, conversation_store.get(db, root.id), call.tool_calls[0], 1, _must_not_run)
    assert replay.outcome.status == "SUCCEEDED"
    assert len(list_usage(db, AssetUsageQuery(asset_id=asset.id))) == before + 1
    revoke(db, grant_id)
    denied = delegate(db, conversation_store.get(db, root.id), call.tool_calls[0], 1, _must_not_run)
    assert denied.outcome.status == "FAILED"
    assert "apply for access" in (denied.outcome.error or "")
    assert denied.summary == ""
    assert denied.events == []
    assert denied.outcome.content.root == {}
