# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Old read previews preserve provenance without changing durable or recent messages."""

from datetime import UTC, datetime

import pytest

from datakeel.actions.models import ActionContext, ActionImpact, ActionPlan, ActionRun
from datakeel.core.agent_models import ChatMessage, ToolDefinition
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.models import FrozenManifest, ObjectSet
from datakeel.ontology.tool_history import compact_history
from datakeel.ontology.tool_models import ToolOutcome


def _message(outcome: ToolOutcome) -> ChatMessage:
    return ChatMessage(
        role="tool", name=outcome.name, content=outcome.model_dump_json(), tool_call_id="call"
    )


def _read() -> ToolOutcome:
    return ToolOutcome(
        name="query_evidence",
        status="FAILED",
        error="Partial read",
        invocation_id="invocation-1",
        requires_approval=True,
        asset_refs=[AssetRef(asset_id="dataset-1", version="v1", display_name="样例")],
        content=JsonDocument(
            {
                "rows": [{"id": index, "text": "数据" * 300} for index in range(20)],
                "count": 20,
                "note": "说明" * 300,
                "nested": {"items": [[1, 2, 3], {"hidden": "x" * 300}]},
            }
        ),
    )


def test_old_read_preserves_metadata_counts_and_two_bounded_previews() -> None:
    """Summaries stay deterministic and preserve every outcome field besides content."""
    original = _read()
    message = _message(original)
    folded = compact_history((message,), (), keep_recent_tools=0)[0]
    outcome = ToolOutcome.model_validate_json(folded.content)
    summary = outcome.content.root
    fields = summary["fields"]
    assert isinstance(fields, dict)
    assert summary["folded"] is True
    assert summary["original_bytes"] == len(message.content.encode("utf-8"))
    assert summary["keys"] == list(original.content.root)
    assert fields["rows"] == {
        "item_count": 20,
        "preview": [
            {"keys": ["id", "text"], "item_count": 2, "preview": {"id": i, "text": "数据" * 120}}
            for i in range(2)
        ],
    }
    assert fields["count"] == 20
    assert fields["note"] == "说明" * 120
    assert fields["nested"] == {
        "keys": ["items"],
        "item_count": 1,
        "preview": {
            "items": {
                "item_count": 2,
                "preview": [
                    {"item_count": 3, "preview": []},
                    {"keys": ["hidden"], "item_count": 1, "preview": {}},
                ],
            }
        },
    }
    assert outcome.model_dump(exclude={"content"}) == original.model_dump(exclude={"content"})
    assert folded.tool_call_id == message.tool_call_id
    assert compact_history((message,), (), keep_recent_tools=0) == [folded]
    assert message.content == original.model_dump_json()
    assert len(folded.content.encode("utf-8")) < len(message.content.encode("utf-8")) // 5


@pytest.mark.parametrize("keep_recent", [0, -1])
def test_byte_threshold_counts_utf8_and_zero_recent_keeps_no_messages(keep_recent: int) -> None:
    """The serialized byte threshold is inclusive and does not count Unicode characters."""
    message = _message(_read())
    assert compact_history(
        [message], [], keep_recent_tools=keep_recent, max_tool_bytes=len(message.content.encode())
    ) == [message]
    folded = compact_history(
        [message], [], keep_recent_tools=keep_recent, max_tool_bytes=len(message.content)
    )[0]
    assert ToolOutcome.model_validate_json(folded.content).content.root["folded"] is True


def test_discovery_does_not_displace_recent_reads_and_retains_search_metadata() -> None:
    """Interleaved discoveries lose duplicate schemas without consuming the recent window."""
    tool = ToolDefinition(
        name="read", description="Read", parameters=JsonDocument({"type": "object"})
    )
    search = _message(
        ToolOutcome(
            name="tool_search",
            status="SUCCEEDED",
            content=JsonDocument(
                {"tools": [tool.model_dump(mode="json")], "total_matches": 12, "truncated": True}
            ),
        )
    )
    old, recent = _message(_read()), _message(_read())
    folded = compact_history([old, search, recent, search], [tool], keep_recent_tools=1)
    assert ToolOutcome.model_validate_json(folded[0].content).content.root["folded"] is True
    assert folded[2] is recent
    assert folded[1] == folded[3]
    assert ToolOutcome.model_validate_json(folded[1].content).content.root == {
        "tools": [{"name": "read", "description": "Read"}],
        "total_matches": 12,
        "truncated": True,
    }


def test_small_legacy_and_non_tool_messages_stay_unchanged() -> None:
    """Invalid read outcomes and non-tool text are never interpreted or rewritten."""
    messages = [
        ChatMessage(role="user", content="x" * 3000),
        ChatMessage(role="assistant", content="y" * 3000),
        ChatMessage(role="tool", name="legacy", content="z" * 3000),
        _message(ToolOutcome(name="read", status="SUCCEEDED", content=JsonDocument({"count": 1}))),
        _message(ToolOutcome(name="tool_search", status="FAILED", error="No search result")),
    ]
    assert compact_history(messages, [], keep_recent_tools=0) == messages
    assert compact_history([], []) == []


def test_recent_window_counts_failed_and_legacy_tools() -> None:
    """All non-discovery tool exchanges count even when their output cannot be folded."""
    old = _message(_read())
    recent = [ChatMessage(role="tool", name="legacy", content="legacy") for _ in range(4)]
    result = compact_history([old, *recent], [])
    assert ToolOutcome.model_validate_json(result[0].content).content.root["folded"] is True
    assert result[1:] == recent
    assert compact_history([old], [])[0] is old


def _plan() -> ActionPlan:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    return ActionPlan(
        id="plan",
        action_type="quarantine_files",
        canonical_params={},
        manifest=FrozenManifest(query=ObjectSet(), objects=[], state_digest="state", total_bytes=0),
        plan_digest="plan",
        target_digest="target",
        state_digest="state",
        created_at=at,
        expires_at=at,
        reversible=True,
        external=False,
        impact=ActionImpact(object_count=0, total_bytes=0, external=False),
        actor="local",
        context=ActionContext(),
    )


@pytest.mark.parametrize("field", ["plan", "run"])
def test_action_plans_and_runs_are_verbatim_even_outside_recent_window(field: str) -> None:
    """Approval and execution evidence stays complete regardless of output size or age."""
    plan = _plan()
    run = ActionRun(
        id="run",
        plan_id=plan.id,
        action_type=plan.action_type,
        status="SUCCEEDED",
        created_at=plan.created_at,
    )
    outcome = _read().model_copy(update={field: plan if field == "plan" else run})
    message = _message(outcome)
    assert compact_history([message], [], keep_recent_tools=0)[0] is message
