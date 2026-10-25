# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image goldens exercise actual explanations, replay batches and external approval boundaries."""

import socket
from pathlib import Path

import pytest

from datakeel.actions.service import list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.harness.assessment import assess
from datakeel.harness.cases import bind_case, load_cases
from datakeel.harness.execution import observe_case, run_case
from datakeel.harness.image_kg_cases import seed_image_kg_case
from datakeel.storage.database import Database


@pytest.mark.parametrize(
    "identifier", ["41-image-kg-explain", "42-image-kg-replay", "43-image-kg-external"]
)
def test_image_goldens_use_offline_sources_and_actual_policy(
    identifier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No replay or preparation step may initialize a real model client."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Image golden attempted network or credential access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", forbidden)
    case = next(item for item in load_cases() if item.id == identifier)
    report = run_case(case, "fake")
    assert report.passed, report.failures


def test_external_vision_prepare_keeps_conversation_action_executions_at_zero(
    db: Database, tmp_path: Path
) -> None:
    """Successful replay fixture setup must never conceal an external model execution."""
    fixture = seed_image_kg_case(db, tmp_path)
    baseline = list_runs(db)
    case = bind_case(
        next(item for item in load_cases() if item.id == "43-image-kg-external"), fixture
    )
    observation = observe_case(db, case, FakeProvider([]))
    assert observation.runs == []
    assert list_runs(db) == baseline
    plan = observation.plans[0]
    assert plan.requires_approval
    assert plan.impact.transcription_estimate is not None
    assert plan.impact.transcription_estimate.images == 2
    assert plan.impact.transcription_estimate.image_tokens > 0
    assert plan.impact.kg_estimate is not None
    assert plan.impact.kg_estimate.extraction_input_basis == "transcription_limit"
    assert assess(case.expect, observation).passed
