# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assert answer-state and candidate-ID boundaries using measured rejected payloads."""

from datetime import UTC, datetime

from pydantic import ValidationError

from datakeel.agent.providers import FakeProvider
from datakeel.ask.rerank import rerank_candidates
from datakeel.core.agent_models import ModelResponse
from datakeel.core.ask_models import AskAnswer, RerankRequest
from datakeel.core.metric_models import QueryResult


def test_model_sql_cannot_cross_candidate_id_boundary() -> None:
    """Even schema-shaped model SQL remains outside the supplied candidate identity set."""
    provider = FakeProvider(
        [ModelResponse(content='{"ordered_ids":["SELECT SUM(amount) FROM orders", "revenue"]}')]
    )
    result = rerank_candidates(
        provider,
        RerankRequest(question="收入", candidate_ids=("revenue", "booked_sales")),
    )
    assert result.ordered_ids == ("revenue", "booked_sales")
    assert provider.requests[0].tools == []


def test_unanswerable_cannot_publish_a_guessed_numeric_answer() -> None:
    """A real model-validation boundary rejects values attached to an unanswered question."""
    rejected = False
    try:
        AskAnswer(
            session_id="unknown-metric",
            question="退货率为什么上升",
            status="unanswerable",
            message="猜测答案为 42。",
            reference_instant=datetime(2026, 10, 1, tzinfo=UTC),
            result=QueryResult(columns=["guessed_value"], rows=[[42]]),
        )
    except ValidationError as error:
        rejected = "Non-answer states must never include" in str(error)
    assert rejected, "Unanswerable response admitted an invented numerical answer"
