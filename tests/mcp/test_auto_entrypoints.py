# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real MCP discovery and dispatch preserve automatic preparation and image overrides."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastmcp import Client
from jsonschema import Draft202012Validator

from datakeel.actions.service import list_runs
from datakeel.core.models import JsonDocument
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.tool_invocations import list_invocations
from tests.api.test_auto_entrypoints import (
    assert_frozen_auto_plan,
    auto_profile,
    block_transcription_backends,
)
from tests.worker.image_helpers import image_dataset

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_mcp_auto_tool_schema_and_dispatch_prepare_without_transcription(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real protocol call reaches durable preparation with auto and two explicit overrides."""
    dataset = image_dataset(db, tmp_path, count=3)
    profile = auto_profile(monkeypatch)
    block_transcription_backends(monkeypatch)
    arguments = JsonDocument(
        {
            "dataset_id": dataset.dataset_id,
            "version_id": dataset.version_id,
            "profile_id": "fake",
            "transcription_profile_id": profile.id,
            "transcription_mode": "auto",
            "mode_overrides": {dataset.files[1].id: "ocr", dataset.files[2].id: "vlm"},
        }
    )

    async def scenario() -> ToolOutcome:
        async with Client(create_server(db), mode="legacy") as client:
            tools = {tool.name: tool for tool in await client.list_tools()}
            schema = tools["run_kg_extraction"].input_schema
            assert schema["properties"]["transcription_mode"]["anyOf"][0]["enum"] == [
                "ocr",
                "vlm",
                "auto",
            ]
            assert schema["properties"]["mode_overrides"]["additionalProperties"]["enum"] == [
                "ocr",
                "vlm",
                "auto",
            ]
            Draft202012Validator(schema).validate(arguments.root)
            response = await client.call_tool(
                "run_kg_extraction",
                arguments.root,
                raise_on_error=False,
            )
            assert not response.is_error
            return ToolOutcome.model_validate(response.structured_content)

    outcome = asyncio.run(scenario())
    assert outcome.status == "SUCCEEDED", outcome.error
    assert outcome.plan is not None
    assert_frozen_auto_plan(outcome.plan, dataset, profile)
    assert outcome.requires_approval
    assert outcome.plan.agent_id
    assert outcome.plan.session_id
    assert list_runs(db) == []
    invocation = list_invocations(db)[0]
    assert invocation.status == "SUCCEEDED"
    assert invocation.name == "run_kg_extraction"
    assert invocation.id == outcome.invocation_id


def test_mcp_auto_invalid_mode_is_audited_without_backend_or_execution(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protocol rejection remains visible and cannot trigger an OCR attempt."""
    dataset = image_dataset(db, tmp_path)
    profile = auto_profile(monkeypatch)
    block_transcription_backends(monkeypatch)

    async def scenario() -> ToolOutcome:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool(
                "run_kg_extraction",
                {
                    "dataset_id": dataset.dataset_id,
                    "version_id": dataset.version_id,
                    "profile_id": "fake",
                    "transcription_profile_id": profile.id,
                    "transcription_mode": "automatic",
                },
                raise_on_error=False,
            )
            assert response.is_error
            return ToolOutcome.model_validate(response.structured_content)

    outcome = asyncio.run(scenario())
    assert outcome.status == "FAILED"
    assert outcome.plan is None
    assert outcome.error
    assert "transcription_mode" in outcome.error
    assert list_runs(db) == []
    assert list_invocations(db)[0].status == "FAILED"
