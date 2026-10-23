# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline evidence conversations inspect real observations before controlled actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions.service import list_approvals, list_runs
from datakeel.agent.evidence_demo import respond_evidence
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ChatMessage, ConversationCreate, MessageInput, ModelRequest
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.models import JsonDocument
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.evidence_queries import query_evidence
from tests.evidence.interface_fixtures import seed_query_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.agent.models import AgentEvent
    from datakeel.storage.database import Database


def _turn(db: Database, conversation: str, text: str) -> list[AgentEvent]:
    events = list(send_message(db, conversation, MessageInput(content=text)))
    assert events[-1].event == "done"
    assert not any(
        event.stop_reason in {"budget_exceeded", "provider_error", "execution_failed"}
        for event in events
    )
    return events


def test_evidence_query_then_version_and_delete_uses_returned_ids_and_human_gate(
    db: Database, tmp_path: Path
) -> None:
    """Keep the real offline conversation useful without scripted provider answers."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset))
    query = _turn(db, conversation.id, "找出 val 里 caption 提到行人但标注没有 person 的证据")
    outcome = next(event.outcome for event in query if event.event == "tool_result")
    assert outcome is not None
    items = outcome.content.root["data"]["items"]
    expected_ids = {item["asset_ref"]["asset_id"] for item in items}
    version = _turn(db, conversation.id, "对这些样本生成新版本")
    plan = next(event.outcome.plan for event in version if event.event == "plan")
    assert {item.asset_ref.asset_id for item in plan.manifest.objects} == expected_ids
    assert list_runs(db)[0].status == "SUCCEEDED"
    deletion = _turn(db, conversation.id, "删除这些样本")
    assert deletion[-2].stop_reason == "approval_required"
    assert len(list_runs(db)) == 1
    assert list_approvals(db)[0].action_type == "delete_files"


def test_explain_missing_annotation_returns_actual_unknown_tool_text(
    db: Database, tmp_path: Path
) -> None:
    """Use a measured unknown observation rather than a scripted assertion of absence."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset))
    events = _turn(db, conversation.id, "解释无标注样本的证据")
    assert [event.call.name for event in events if event.call] == [
        "query_evidence",
        "explain_sample",
    ]
    text = events[-2].text or ""
    assert "label_gap person: 未知" in text
    assert "unknown" in text
    assert "没有 person" not in text


def test_evidence_selection_quarantine_and_inverse_are_real_reversible_actions(
    db: Database, tmp_path: Path
) -> None:
    """Retain the displayed selection across a follow-up inverse action."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    conversation = create_conversation(
        db, ConversationCreate(dataset_id=dataset, budget=BudgetLimits(conversation_tokens=500000))
    )
    _turn(db, conversation.id, "把缺少标注的证据样本隔离")
    inverse = _turn(db, conversation.id, "取消隔离这些样本")
    assert {run.action_type for run in list_runs(db)} == {"quarantine_files", "unquarantine_files"}
    assert "执行回执已保存" in (inverse[-2].text or "")


def test_evidence_query_without_matching_assets_makes_no_absence_claim(db: Database) -> None:
    """An empty evidence page reports its limitation without inventing observed facts."""
    conversation = create_conversation(db, ConversationCreate())
    events = _turn(db, conversation.id, "查找行人标注缺口和 train 近重复")
    assert "未返回证据样本" in (events[-2].text or "")
    assert not list_runs(db)


def test_evidence_page_across_datasets_requires_explicit_scope_before_action(
    db: Database, tmp_path: Path
) -> None:
    """Never widen one displayed page into an ambiguous cross-dataset version operation."""
    seed_query_evidence(db, tmp_path / "first")
    seed_query_evidence(db, tmp_path / "second")
    result = query_evidence(db, EvidenceQuery(page_size=200))
    outcome = ToolOutcome(
        name="query_evidence",
        status="SUCCEEDED",
        content=JsonDocument({"data": result.model_dump(mode="json")}),
    )
    request = ModelRequest(
        model="fake-script",
        messages=[
            ChatMessage(role="tool", name="query_evidence", content=outcome.model_dump_json())
        ],
        tools=[],
        segments=[],
    )
    response = respond_evidence(request, "生成新版本", JsonDocument({}), [])
    assert response is not None
    assert "选择一个数据集和来源版本" in response.content
    assert not list_runs(db)
