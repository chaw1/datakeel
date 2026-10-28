# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Previously granted data cannot escape through saved answers or tool-call replay."""

from pathlib import Path

from fastapi.testclient import TestClient

from datakeel.agent.service import create_conversation
from datakeel.agent.tools import ToolCatalog
from datakeel.api.app import create_app
from datakeel.core.agent_models import ConversationCreate, ToolCall
from datakeel.core.data_asset_models import AssetUsageQuery
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.conversation_store import get
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database
from tests.assets.entry_helpers import grant, publish, revoke, seed_resources


def test_revoked_answer_and_tool_replays_are_rechecked(db: Database, tmp_path: Path) -> None:
    """The protocol cache and Agent catalog shortcut both obey current grants."""
    resources = seed_resources(db, tmp_path)
    metric = publish(db, AssetRef(asset_type="metric", asset_id="retail_revenue"))
    dataset = publish(db, AssetRef(asset_id=resources.dataset_id))
    metric_grant = grant(db, metric, "valid", "query")
    dataset_grant = grant(db, dataset, "valid", "query")
    assert metric_grant
    assert dataset_grant
    client = TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"})
    response = client.post(
        "/api/ask",
        json={
            "question": "上个季度华东区零售额是多少",
            "actor": "local",
            "reference_instant": "2026-10-01T00:00:00Z",
        },
    )
    assert response.status_code == 200
    answer_id = response.json()["id"]
    conversation = create_conversation(db, ConversationCreate())
    catalog = ToolCatalog(get(db, conversation.id))
    context = ToolCallContext(session_id=conversation.id)
    arguments = JsonDocument({"dataset_id": resources.dataset_id})
    call = ToolCall(id="read-once", name="search_files", arguments=arguments)
    assert catalog.invoke(db, call, context).status == "SUCCEEDED"
    assert invoke_tool(db, call.name, arguments, context, call_id=call.id).status == "SUCCEEDED"
    before = len(list_usage(db, AssetUsageQuery()))
    revoke(db, metric_grant)
    revoke(db, dataset_grant)
    replay = client.get(f"/api/ask/{answer_id}")
    assert replay.status_code == 403
    assert "4979475" not in replay.text
    for outcome in (
        invoke_tool(db, call.name, arguments, context, call_id=call.id),
        catalog.invoke(db, call, context),
    ):
        assert outcome.status == "FAILED"
        assert outcome.content.root == {}
        assert "apply for access" in (outcome.error or "")
    assert len(list_usage(db, AssetUsageQuery())) == before


def test_tool_actor_is_bound_to_platform_context_not_nested_ask_input(
    db: Database, tmp_path: Path
) -> None:
    """A caller cannot borrow a named subject's grant by filling AskRequest.actor."""
    seed_resources(db, tmp_path)
    metric = publish(db, AssetRef(asset_type="metric", asset_id="retail_revenue"))
    assert grant(db, metric, "valid", "query", subject="ungranted-input")
    arguments = JsonDocument(
        {
            "question": "上个季度华东区零售额是多少",
            "actor": "ungranted-input",
            "reference_instant": "2026-10-01T00:00:00Z",
        }
    )
    denied = invoke_tool(db, "ask_data", arguments, ToolCallContext())
    assert denied.status == "FAILED"
    assert denied.content.root == {}
    assert list_usage(db, AssetUsageQuery(asset_id=metric.id)) == ()
    assert grant(db, metric, "valid", "query")
    result = invoke_tool(
        db,
        "ask_data",
        arguments,
        ToolCallContext(),
    )
    assert result.status == "SUCCEEDED"
    usages = list_usage(db, AssetUsageQuery(asset_id=metric.id))
    assert len(usages) == 1
    assert usages[0].actor == "local"
    assert usages[0].entry == "agent"
