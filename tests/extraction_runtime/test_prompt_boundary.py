# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind approved prompt estimates to actual metered requests without model network access."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.models import JsonDocument
from datakeel.extraction_runtime.adapter import llm_extractor
from datakeel.kg.loader import get_profile
from datakeel.kg.prompt import extraction_prompt
from datakeel.storage.budget_rows import BudgetReservationRow
from datakeel.storage.kg_preparation import read_documents
from tests.kg.integration_helpers import execute_graph, prepare_graph, text_dataset

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from datakeel.core.kg_contracts import ExtractionProfile
    from datakeel.extraction_runtime.adapter import LLMExtractor
    from datakeel.storage.database import Database


def _check_request(
    request: httpx.Request,
    db: Database,
    expected: list[str],
    captured: list[str],
    max_output_tokens: int,
) -> httpx.Response:
    payload = JsonDocument.model_validate_json(request.content)
    messages = payload.root["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 1
    message = messages[0]
    assert isinstance(message, dict)
    assert message["role"] == "user"
    content = message["content"]
    assert isinstance(content, str)
    assert content == expected[len(captured)]
    with db.session() as session:
        reservations = session.scalars(
            select(BudgetReservationRow).where(BudgetReservationRow.status == "RESERVED")
        ).all()
        assert len(reservations) == 1
        assert reservations[0].tokens == estimate_tokens(content) + max_output_tokens
    captured.append(content)
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": '{"entities":[],"relations":[]}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 13, "completion_tokens": 5},
        },
    )


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    profile: ExtractionProfile,
    respond: Callable[[httpx.Request], httpx.Response],
) -> None:
    @contextmanager
    def factory(*_args: object, **_kwargs: object) -> Iterator[LLMExtractor]:
        with (
            httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
            llm_extractor(profile, "fixture-key", client) as extractor,
        ):
            yield extractor

    monkeypatch.setattr("datakeel.worker.kg_runner.create_extractor", factory)


@pytest.mark.parametrize("profile_id", ["ollama", "cloud"])
def test_approved_estimate_matches_each_reserved_and_transmitted_prompt(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile_id: str
) -> None:
    """Run prepare, approval and worker against the SDK's injected synthetic HTTP peer."""
    profile = get_profile(profile_id).model_copy(
        update={
            "base_url": "https://fixture.invalid/v1",
            "api_key_env": None,
            "chunk_size": 64,
            "chunk_overlap": 8,
            "max_output_tokens": 128,
        }
    )
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: profile)
    dataset = text_dataset(
        db,
        tmp_path,
        (
            (
                "Cedar uses Reed. Birch uses Grass. Elm uses Moss. Pine uses Fern. "
                "Maple uses Clover. Oak uses Iris. Willow uses Lily."
            ),
            "Juniper uses Heather.",
        ),
    )
    plan = prepare_graph(db, dataset, profile_id)
    params = RunKGExtractionParams.model_validate(plan.canonical_params)
    assert params.prepared is not None
    prepared = params.prepared
    with db.session() as session:
        documents = read_documents(session, params, prepared.profile)
    expected = [
        extraction_prompt(block, prepared.schema_definition)
        for document in documents
        for block in document.blocks
    ]
    captured: list[str] = []
    _install_transport(
        monkeypatch,
        prepared.profile,
        lambda request: _check_request(request, db, expected, captured, profile.max_output_tokens),
    )
    assert plan.requires_approval
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert run.status == "completed"
    assert len(captured) == prepared.estimate.blocks > 1
    assert prepared.estimate.input_tokens == sum(estimate_tokens(prompt) for prompt in captured)
    assert run.report.model_calls == len(captured)
    for prompt in captured:
        assert all(example.text in prompt for example in prepared.schema_definition.examples)
