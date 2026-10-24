# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""New knowledge boundaries preserve metric validation and reject fabricated answer states."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from datakeel.core.ask_models import AskAnswer
from datakeel.core.knowledge_models import KnowledgeAnswer, KnowledgeOtherEnd
from datakeel.core.models import JsonDocument
from tests.ask.knowledge_helpers import claim_context


def _answer() -> JsonDocument:
    return JsonDocument(
        {
            "session_id": "s",
            "question": "Who owns Revenue?",
            "status": "unanswerable",
            "message": "Missing",
            "reference_instant": datetime(2026, 10, 1, tzinfo=UTC).isoformat(),
            "answer_kind": "knowledge",
            "knowledge": KnowledgeAnswer(intent="owner", reason_code="unknown_subject").model_dump(
                mode="json"
            ),
        }
    )


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"question": "e\u0301"}, "NFC"),
        (
            {
                "matches": [
                    {
                        "start": 0,
                        "end": 5,
                        "text": "wrong",
                        "source": "fixture",
                        "match_kind": "exact",
                    }
                ]
            },
            "does not address",
        ),
        ({"knowledge": None}, "typed knowledge"),
        ({"result": {"columns": ["value"], "rows": [[99]]}}, "metric execution"),
        ({"status": "answered"}, "at least one fact"),
        ({"status": "clarification"}, "multiple subject"),
        ({"knowledge": {"intent": "owner"}}, "reason code"),
    ],
)
def test_knowledge_answers_validate_their_own_states(
    changes: dict[str, object], error: str
) -> None:
    """Knowledge requests cannot exploit the metric bypass to publish unevidenced facts."""
    payload: dict[str, object] = dict(_answer().root)
    payload.update(changes)
    with pytest.raises(ValidationError, match=error):
        AskAnswer.model_validate(payload)


def test_other_endpoint_requires_exactly_the_linked_receipt_fields() -> None:
    """Linked and unlinked endpoints are mutually exclusive public states."""
    subject, context = claim_context()
    entity = context.entities[1]
    with pytest.raises(ValidationError, match="require an asset"):
        KnowledgeOtherEnd(status="linked", entity=entity)
    with pytest.raises(ValidationError, match="cannot assert"):
        KnowledgeOtherEnd(status="not_in_catalog", entity=entity, asset_ref=subject.asset_ref)
