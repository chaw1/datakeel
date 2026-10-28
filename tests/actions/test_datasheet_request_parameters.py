# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Approved datasheet model calls carry the same typed request parameters as transcription."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from datakeel.actions.datasheet_parameters import GenerateDatasheetParams, GenerateDatasheetRequest
from datakeel.worker.datasheet_runner import execute_datasheet
from tests.actions.test_datasheet_security import (
    FixtureProvider,
    _input,
    _prepare,
    _response,
    _schedule,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from pydantic import JsonValue

    from datakeel.core.agent_models import ConversationCreate, Provider
    from datakeel.storage.database import Database
    from tests.actions.conftest import DatasetFixture


def test_request_accepts_transcription_style_thinking_controls() -> None:
    """enable_thinking and reasoning_effort are typed exactly as in transcription profiles."""
    request = GenerateDatasheetRequest(
        version_id="v1",
        mode="model",
        provider="openai",
        model="qwen3.5-flash",
        request_parameters={"enable_thinking": False, "reasoning_effort": "low"},
    )
    assert request.request_parameters == {"enable_thinking": False, "reasoning_effort": "low"}


@pytest.mark.parametrize(
    "values",
    [
        {"request_parameters": {"api_key": "hidden"}},
        {"request_parameters": {"enable_thinking": "false"}},
        {"request_parameters": {"reasoning_effort": "unlimited"}},
        {"request_parameters": {"num_ctx": 16384}},
        {"request_parameters": {"enable_thinking": False}, "provider": "anthropic"},
        {"request_parameters": {"enable_thinking": False}, "provider": "fake"},
        {"request_parameters": {"enable_thinking": False}, "mode": "template"},
    ],
)
def test_request_rejects_overrides_and_parameters_without_an_openai_model(
    values: dict[str, object],
) -> None:
    """Unknown names, loose types, Ollama-only context and non-OpenAI targets are refused."""
    base: dict[str, object] = {
        "version_id": "v1",
        "mode": "model",
        "provider": "openai",
        "model": "qwen3.5-flash",
    }
    with pytest.raises(ValidationError, match="request_parameters"):
        GenerateDatasheetRequest.model_validate({**base, **values})


def test_plan_freezes_parameters_and_worker_passes_them_to_the_provider(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reviewed plan binds the parameters and the approved call uses exactly those values."""
    plan = _prepare(
        db,
        dataset,
        provider="openai",
        model="qwen3.5-flash",
        request_parameters={"enable_thinking": False},
    )
    params = GenerateDatasheetParams.model_validate(plan.canonical_params)
    assert params.prepared is not None
    assert params.prepared.request_parameters == {"enable_thinking": False}
    assert params.prepared.price is not None
    assert params.prepared.price.model == "qwen3.5-flash"
    seen: list[Mapping[str, JsonValue] | None] = []

    @contextmanager
    def session(
        config: ConversationCreate,
        supplied: Provider | None = None,
        request_parameters: Mapping[str, JsonValue] | None = None,
    ) -> Generator[Provider]:
        assert config.model == "qwen3.5-flash"
        assert supplied is not None
        seen.append(request_parameters)
        yield supplied

    monkeypatch.setattr("datakeel.runtime.datasheet_model.provider_session", session)
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    _job, prepared = _input(db, lease)
    assert prepared.request_parameters == {"enable_thinking": False}
    assert execute_datasheet(queue, lease, FixtureProvider(_response(prepared)))
    assert seen == [{"enable_thinking": False}]
