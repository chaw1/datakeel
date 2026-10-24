# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Graph golden conversations use real preparation, worker results and source explanations."""

import socket
from pathlib import Path

import pytest

from datakeel.actions.service import list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.harness.assessment import assess
from datakeel.harness.cases import bind_case, load_cases
from datakeel.harness.execution import observe_case, run_case
from datakeel.harness.kg_cases import seed_kg_case
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces


@pytest.mark.parametrize(
    "identifier",
    ["33-kg-query", "34-kg-explain-review", "35-kg-replay-action", "36-kg-external-approval"],
)
def test_graph_goldens_run_without_network_or_credentials(
    identifier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise actual read tools and approval decisions under socket and secret guards."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Offline graph golden attempted a network connection or credential read")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    case = next(item for item in load_cases() if item.id == identifier)
    report = run_case(case, "fake")
    assert report.passed, report.failures
    assert report.turns <= case.expect.max_turns


def test_fixture_action_is_excluded_from_external_conversation_execution_count(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One successfully seeded replay cannot conceal or contaminate zero outbound executions."""
    fixture = seed_kg_case(db, tmp_path)
    baseline = list_runs(db)
    assert len(baseline) == 1
    assert baseline[0].status == "SUCCEEDED"
    extraction_traces = list_traces(db)
    assert len(extraction_traces) == 1
    assert extraction_traces[0].call_type == "extraction"
    assert extraction_traces[0].cost_usd == 0
    case = bind_case(
        next(item for item in load_cases() if item.id == "36-kg-external-approval"), fixture
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Awaiting approval must not construct an external extractor")

    monkeypatch.setattr("datakeel.extraction_runtime.factory.create_extractor", forbidden)
    observation = observe_case(db, case, FakeProvider([]))
    assert observation.runs == []
    assert list_runs(db) == baseline
    assert observation.plans[0].requires_approval
    assert assess(case.expect, observation).passed
