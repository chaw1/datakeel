# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Signed graph plans disclose fingerprints while execution verifies all source bytes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Never

import pytest
from fastmcp import Client

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan
from datakeel.agent.dispatch import ToolDispatcher
from datakeel.agent.guards import LoopGuard
from datakeel.core.agent_models import ConversationCreate, MessageInput, ToolCall
from datakeel.core.kg_models import TextBlock
from datakeel.core.models import JsonDocument
from datakeel.kg.loader import contracts_path, get_profile, get_schema
from datakeel.kg.text import chunk_text
from datakeel.kg_eval.loader import load_cases
from datakeel.mcp import create_server
from datakeel.storage import conversation_store
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_store import get_job, list_runs
from datakeel.storage.objects import object_store
from datakeel.worker.runner import run_worker
from tests.kg.integration_helpers import install_adapter, prepare_graph, text_dataset

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.fixture(autouse=True)
def forbid_extraction_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consent preparation and rejected fingerprints must never access extraction secrets."""

    def forbidden(*_args: object, **_kwargs: object) -> Never:
        pytest.fail("Extraction credentials were read before verified execution")

    monkeypatch.setattr("datakeel.core.settings.Settings.extraction_key", forbidden)


def _arguments(db: Database, tmp_path: Path, profile: str) -> tuple[JsonDocument, str]:
    suite, _ = load_cases(get_schema())
    text = suite.cases[2].text
    dataset = text_dataset(db, tmp_path, (text,))
    return JsonDocument(
        {
            "dataset_id": dataset.dataset_id,
            "version_id": dataset.version_id,
            "profile_id": profile,
        }
    ), text


def _assert_private(payload: str, text: str) -> None:
    assert text not in payload
    assert "text_hash" not in payload
    assert "recorded_at" not in payload
    assert '"original"' not in payload
    assert "content_revision" in payload
    assert "content_hash" in payload
    assert len(payload.encode()) < 24000


@pytest.mark.parametrize("profile", ["replay-demo", "cloud"])
def test_agent_graph_tool_message_contains_only_source_fingerprints(
    db: Database, tmp_path: Path, profile: str
) -> None:
    """Actual tool dispatch never puts demo source or replay responses into chat history."""
    arguments, text = _arguments(db, tmp_path, profile)
    conversation = conversation_store.create(db, ConversationCreate())
    lease = conversation_store.begin(
        db, conversation.id, MessageInput(content="Prepare extraction", idempotency_key="prepare")
    )
    dispatcher = ToolDispatcher(db, conversation.id, lease.token, LoopGuard())
    dispatcher.dispatch(
        ToolCall(name="tool_search", arguments=JsonDocument({"query": "run_kg_extraction"})),
        dry_run=True,
    )
    events, _ = dispatcher.dispatch(
        ToolCall(name="run_kg_extraction", arguments=arguments), dry_run=True
    )
    assert any(event.event == "plan" for event in events)
    message = conversation_store.get(db, conversation.id).messages[-1]
    assert message.role == "tool"
    _assert_private(message.content, text)
    assert list_runs(db) == ()


@pytest.mark.parametrize("profile", ["replay-demo", "cloud"])
def test_mcp_graph_tool_returns_fingerprints_without_demo_source_or_recording(
    db: Database, tmp_path: Path, profile: str
) -> None:
    """The actual MCP protocol result remains bounded and contains no extraction payloads."""
    arguments, text = _arguments(db, tmp_path, profile)

    async def scenario() -> str:
        async with Client(create_server(db), mode="legacy") as client:
            result = await client.call_tool("run_kg_extraction", arguments.root)
            assert not result.is_error
            return JsonDocument.model_validate(result.structured_content).model_dump_json()

    _assert_private(asyncio.run(scenario()), text)
    assert list_runs(db) == ()


def test_changed_source_after_approval_fails_before_any_provider_call(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A later document cannot replace the exact bytes covered by human consent."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.", "Beta uses Widget."))
    adapter = install_adapter(monkeypatch, ())
    plan = prepare_graph(db, dataset, "cloud")
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    key = dataset.files[1].metadata["object_key"]
    assert isinstance(key, str)
    object_store().materialize(key).write_text("Changed source", encoding="utf-8")
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run_worker(db, once=True)
    run = list_runs(db)[0]
    assert run.status == "failed"
    assert "approved inputs" in (run.report.error or "")
    assert adapter.calls == 0
    assert list_traces(db, run.id) == []


def test_changed_recording_after_preparation_fails_before_provider_construction(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay content must match its signed hash even when its parsed records are unchanged."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    recording = tmp_path / "recording.yaml"
    recording.write_bytes((contracts_path() / "recordings/qwen3.5.yaml").read_bytes())
    profile = get_profile("replay-demo").model_copy(update={"recording": str(recording)})
    monkeypatch.setattr(
        "datakeel.storage.kg_preparation.get_profile", lambda _id="replay-demo": profile
    )
    adapter = install_adapter(monkeypatch, ())
    plan = prepare_graph(db, dataset, "replay-demo")
    recording.write_text(recording.read_text() + "\n# Changed recording bytes\n")
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run_worker(db, once=True)
    run = list_runs(db)[0]
    assert run.status == "failed"
    assert "fingerprints changed" in (run.report.error or "")
    assert adapter.calls == 0


@pytest.mark.parametrize("changed", ["offset", "text"])
def test_changed_chunk_fingerprint_aborts_before_constructing_a_provider(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    """Rehydration must compare chunk positions and content even when source bytes agree."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.", "Beta uses Widget."))
    plan = prepare_graph(db, dataset, "cloud")
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))

    def changed_blocks(text: str, size: int, overlap: int = 0) -> tuple[TextBlock, ...]:
        blocks = chunk_text(text, size, overlap)
        block = blocks[-1]
        altered = (
            TextBlock(text=block.text, start=block.start + 1, end=block.end + 1)
            if changed == "offset"
            else TextBlock(text="X" + block.text[1:], start=block.start, end=block.end)
        )
        return (*blocks[:-1], altered)

    def forbidden(*_args: object, **_kwargs: object) -> Never:
        pytest.fail("A mismatched fingerprint reached provider construction")

    monkeypatch.setattr("datakeel.storage.kg_preparation.chunk_text", changed_blocks)
    monkeypatch.setattr("datakeel.worker.kg_runner.create_extractor", forbidden)
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run_worker(db, once=True)
    run = list_runs(db)[0]
    assert run.status == "failed"
    assert "fingerprints changed" in (run.report.error or "")
    assert run.report.unexecuted == 2
    assert list_traces(db, run.id) == []
    assert get_job(db, run.id).documents == ()
