# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Answer boundaries forbid guessed values and validate exact evidence positions."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from datakeel.core.ask_models import AskAnswer, AskRequest, LineageReference, MatchEvidence
from datakeel.core.metric_models import CompiledQuery, MetricCard, QueryResult, SemanticLayer


def answered_fixture(layer: SemanticLayer) -> AskAnswer:
    """Construct a complete answer for independent boundary validation."""
    metric = layer.metrics[0]
    return AskAnswer(
        session_id="session",
        question=metric.name,
        status="answered",
        message="Registered query",
        reference_instant=datetime(2026, 10, 1, tzinfo=UTC),
        metric_card=MetricCard(definition=metric),
        sql=CompiledQuery(
            metric_id=metric.id,
            metric_version=1,
            source_id="erp",
            dialect="sqlite",
            sql="SELECT 1",
            tables=[metric.measure.table],
            columns=[metric.measure.column],
        ),
        result=QueryResult(columns=["value"], rows=[[1]]),
        lineage=LineageReference(asset_id=metric.id),
        matches=(
            MatchEvidence(
                start=0,
                end=len(metric.name),
                text=metric.name,
                source="fixture",
                match_kind="exact",
                metric_id=metric.id,
            ),
        ),
    )


def test_request_requires_visible_question_and_aware_reference() -> None:
    """Naive timestamps and blank questions never reach semantic matching."""
    with pytest.raises(ValidationError, match="visible text"):
        AskRequest(question="  ")
    with pytest.raises(ValidationError, match="timezone"):
        AskRequest.model_validate(
            {"question": "零售额", "reference_instant": "2026-10-01T00:00:00"}
        )
    assert AskRequest(question="零售额").reference_instant.tzinfo == UTC


def test_match_evidence_requires_exact_nonempty_character_span() -> None:
    """A malformed span cannot be persisted as matching evidence."""
    with pytest.raises(ValidationError, match="captured text length"):
        MatchEvidence(start=1, end=1, text="x", source="fixture", match_kind="exact")


@pytest.mark.parametrize("status", ["unanswerable", "clarification"])
def test_nonanswer_model_forbids_metric_sql_and_values(layer: SemanticLayer, status: str) -> None:
    """A rejected question cannot accidentally serialize a guessed result."""
    payload = answered_fixture(layer).model_dump()
    payload["status"] = status
    with pytest.raises(ValidationError, match="Non-answer states"):
        AskAnswer.model_validate(payload)


@pytest.mark.parametrize("field", ["metric_card", "sql", "result", "lineage"])
def test_answer_model_requires_complete_evidence(layer: SemanticLayer, field: str) -> None:
    """An answered state cannot omit any evidence category."""
    payload = answered_fixture(layer).model_dump()
    payload[field] = None
    with pytest.raises(ValidationError, match="Answered questions require"):
        AskAnswer.model_validate(payload)


def test_answer_model_rejects_stale_query_revision_and_missing_field_evidence(
    layer: SemanticLayer,
) -> None:
    """Metric revision and SQL evidence identify the same immutable semantic definition."""
    payload = answered_fixture(layer).model_dump()
    payload["sql"]["metric_version"] = 2
    with pytest.raises(ValidationError, match="revisions must agree"):
        AskAnswer.model_validate(payload)
    payload = answered_fixture(layer).model_dump()
    payload["sql"]["columns"] = []
    with pytest.raises(ValidationError, match="table, column"):
        AskAnswer.model_validate(payload)


def test_answer_model_rejects_wrong_nfc_and_misaligned_text(layer: SemanticLayer) -> None:
    """Evidence refers to the exact saved NFC question, including original spacing."""
    payload = answered_fixture(layer).model_dump()
    payload["question"] = "e\u0301"
    with pytest.raises(ValidationError, match="NFC"):
        AskAnswer.model_validate(payload)
    payload["question"] = "different"
    with pytest.raises(ValidationError, match="does not address"):
        AskAnswer.model_validate(payload)
