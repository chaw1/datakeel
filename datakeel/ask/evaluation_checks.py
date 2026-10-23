# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure numeric accuracy and state-appropriate evidence without guessing outcomes."""

import math

from datakeel.core.ask_eval import AskQuestion
from datakeel.core.ask_models import AskAnswer
from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import QueryResult, Scalar
from datakeel.metrics.sql_safety import validate_select

RELATIVE_TOLERANCE = 0.005
_CLARIFICATION_MINIMUM = 2
_SUGGESTIONS_MINIMUM = 3


def scalar_equal(actual: Scalar, expected: Scalar) -> bool:
    """Compare numeric cells within half a percent and other cells by exact value."""
    if isinstance(actual, int | float) and isinstance(expected, int | float):
        return math.isclose(actual, expected, rel_tol=RELATIVE_TOLERANCE, abs_tol=1e-9)
    return actual == expected


def table_equal(actual: QueryResult, expected: QueryResult) -> bool:
    """Compare row multisets without assuming SQL order or losing duplicate rows."""
    if (
        actual.columns != expected.columns
        or len(actual.rows) != len(expected.rows)
        or actual.truncated
    ):
        return False
    remaining = list(actual.rows)
    for expected_row in expected.rows:
        match = next(
            (
                index
                for index, row in enumerate(remaining)
                if len(row) == len(expected_row)
                and all(scalar_equal(a, b) for a, b in zip(row, expected_row, strict=True))
            ),
            None,
        )
        if match is None:
            return False
        remaining.pop(match)
    return True


def correct_answer(question: AskQuestion, answer: AskAnswer, expected_value: float | None) -> bool:
    """Require the expected state, metric identity, and independently computed result."""
    if question.expected_status != answer.status:
        return False
    if answer.status != "answered":
        return (
            answer.result is None
            and answer.sql is None
            and (
                answer.status != "clarification" or len(answer.candidates) >= _CLARIFICATION_MINIMUM
            )
        )
    if (
        answer.metric_card is None
        or answer.result is None
        or answer.metric_card.definition.id != question.metric_id
    ):
        return False
    if question.expected_table is not None:
        return table_equal(answer.result, question.expected_table)
    if len(answer.result.rows) != 1 or len(answer.result.rows[0]) != 1 or expected_value is None:
        return False
    return scalar_equal(answer.result.rows[0][0], expected_value)


def complete_evidence(answer: AskAnswer) -> bool:
    """Measure evidence appropriate to each answer state, including refusals and ambiguity."""
    if not answer.assertions or not answer.assertion_ids:
        return False
    if answer.status == "unanswerable":
        return len(answer.candidates) >= _SUGGESTIONS_MINIMUM and any(
            item.predicate == "ask.unanswerable" for item in answer.assertions
        )
    if answer.status == "clarification":
        return len(answer.candidates) >= _CLARIFICATION_MINIMUM and bool(answer.matches)
    if answer.metric_card is None or answer.sql is None:
        return False
    try:
        validate_select(answer.sql.sql, answer.sql.dialect)
    except ValidationError:
        return False
    metric = answer.metric_card.definition
    return bool(
        metric.id
        and metric.version
        and metric.owner
        and metric.caveats
        and answer.sql.tables
        and answer.sql.columns
        and answer.matches
        and answer.lineage
    )
