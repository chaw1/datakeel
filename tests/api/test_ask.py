# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP answers preserve registered semantics, safe states, and durable replay."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.ask_models import AskAnswer
from datakeel.sample_enterprise import EnterpriseGold
from tests.enterprise_support import enterprise_fixture

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.fixture
def ask_client(db: Database, tmp_path: Path) -> tuple[TestClient, EnterpriseGold]:
    """Use independently generated business-row gold rather than compiler-derived expectations."""
    sample = enterprise_fixture(db, tmp_path / "enterprise")
    return TestClient(create_app(db)), EnterpriseGold.model_validate_json(
        sample.gold_path.read_text()
    )


def test_ask_when_primary_question_matches_gold_and_replays_exact_evidence(
    ask_client: tuple[TestClient, EnterpriseGold],
) -> None:
    """Keep the complete metric revision, SQL, time bounds, match spans, and saved response."""
    client, gold = ask_client
    response = client.post(
        "/api/ask",
        json={
            "question": "上个季度华东区零售额是多少",
            "reference_instant": "2026-10-01T00:00:00Z",
        },
    )
    assert response.status_code == 200
    answer = AskAnswer.model_validate(response.json())
    assert answer.status == "answered"
    assert answer.result is not None
    assert answer.result.rows[0][0] == pytest.approx(gold.answers["ok-east-retail-last-quarter"])
    assert answer.metric_card
    assert answer.metric_card.definition.caveats
    assert answer.sql
    assert answer.sql.tables
    assert answer.sql.columns
    assert answer.sql.sql.upper().startswith("SELECT")
    assert answer.matches
    assert answer.assertions
    assert answer.time_range
    assert answer.time_range.start.isoformat() == "2026-07-01"
    replay = AskAnswer.model_validate(client.get(f"/api/ask/{answer.id}").json())
    assert replay == answer


@pytest.mark.parametrize(
    ("question", "status"),
    [("退货率为什么上升", "unanswerable"), ("上个季度营业额是多少", "clarification")],
)
def test_ask_when_no_single_metric_never_returns_number(
    ask_client: tuple[TestClient, EnterpriseGold], question: str, status: str
) -> None:
    """Unanswerable and ambiguous questions return candidates without fabricated results."""
    client, _ = ask_client
    answer = AskAnswer.model_validate(client.post("/api/ask", json={"question": question}).json())
    assert answer.status == status
    assert answer.result is None
    assert answer.sql is None
    assert len(answer.candidates) >= 2


def test_ask_when_invalid_or_absent_replay_reports_error(
    ask_client: tuple[TestClient, EnterpriseGold],
) -> None:
    """Reject invalid question boundaries and nonexistent saved answers."""
    client, _ = ask_client
    assert client.post("/api/ask", json={"question": " "}).status_code == 422
    assert (
        client.post("/api/ask", json={"question": "零售额", "sql": "DROP TABLE orders"}).status_code
        == 422
    )
    assert client.get("/api/ask/absent").status_code == 404


@pytest.mark.parametrize("question", ["上个季度营业额是多少", "上个季度出货额和零售额是多少"])
def test_ask_when_clarification_is_pinned_answers_original_question_with_registered_metric(
    ask_client: tuple[TestClient, EnterpriseGold],
    question: str,
) -> None:
    """Both shipped clarification cases can select either candidate without rewriting text."""
    client, _ = ask_client
    request = {"question": question, "reference_instant": "2026-10-01T00:00:00Z"}
    first = AskAnswer.model_validate(client.post("/api/ask", json=request).json())
    assert first.status == "clarification"
    assert len(first.candidates) >= 2
    for candidate in first.candidates:
        response = client.post(
            "/api/ask",
            json={**request, "session_id": first.session_id, "metric_id": candidate.definition.id},
        )
        assert response.status_code == 200, response.text
        answer = AskAnswer.model_validate(response.json())
        assert answer.status == "answered"
        assert answer.question == question
        assert answer.session_id == first.session_id
        assert answer.time_range == first.time_range
        assert answer.metric_card == candidate
        assert answer.result is not None
        assert isinstance(answer.result.rows[0][0], int | float)
        assert AskAnswer.model_validate(client.get(f"/api/ask/{answer.id}").json()) == answer


@pytest.mark.parametrize(
    ("question", "metric_id"),
    [
        ("零售额是多少", "missing"),
        ("下个月零售额是多少", "retail_revenue"),
        ("多少", "retail_revenue"),
    ],
)
def test_ask_when_pinned_metric_or_question_is_invalid_never_executes_guessed_query(
    ask_client: tuple[TestClient, EnterpriseGold],
    question: str,
    metric_id: str,
) -> None:
    """A pin bypasses ambiguity only, not metric resolution or temporal validation."""
    client, _ = ask_client
    response = client.post(
        "/api/ask",
        json={
            "question": question,
            "metric_id": metric_id,
            "reference_instant": "2026-10-01T00:00:00Z",
        },
    )
    assert response.status_code == 200
    answer = AskAnswer.model_validate(response.json())
    assert answer.status == "unanswerable"
    assert answer.result is None
    assert answer.sql is None
    assert client.post("/api/ask", json={"question": question, "metric_id": ""}).status_code == 422
