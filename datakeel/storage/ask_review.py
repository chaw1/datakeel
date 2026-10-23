# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind question assertion reviews without selecting or freezing catalog assets."""

from sqlalchemy.orm import Session

from datakeel.core.ask_models import AskAnswer
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.question_models import QuestionProperties
from datakeel.storage.ask_rows import AskAnswerRow
from datakeel.storage.object_projection import content_digest


def question_references(assertion: Assertion) -> list[AssetRef]:
    """Return audited question and semantic endpoints without creating ObjectSets."""
    targets = [assertion.subject]
    if isinstance(assertion.object, AssetRef):
        targets.append(assertion.object)
    if (
        not assertion.predicate.startswith("ask.")
        or assertion.subject.asset_type != "question"
        or assertion.subject.version != assertion.subject.asset_id
        or any(
            ref.asset_type not in {"question", "metric", "term"}
            or ref.namespace != "default"
            or not ref.version
            for ref in targets
        )
    ):
        msg = "Question decisions require versioned local question and semantic endpoints"
        raise ValidationError(msg)
    return targets


def question_review_digest(session: Session, assertions: list[Assertion]) -> str:
    """Freeze exact answer facts in the review digest, leaving the file manifest empty."""
    values: list[JsonDocument] = []
    for assertion in assertions:
        question_references(assertion)
        row = session.get(AskAnswerRow, assertion.subject.asset_id)
        if row is None:
            msg = "Question assertion source answer is unavailable"
            raise ConflictError(msg)
        question = QuestionProperties.model_validate(row.question_payload)
        answer = AskAnswer.model_validate(row.payload)
        if (
            assertion.id not in answer.assertion_ids
            or assertion.subject != question.asset_ref()
            or any(
                anchor.asset_ref != question.asset_ref()
                or anchor.content_revision != question.content_revision
                for anchor in assertion.anchors
            )
        ):
            msg = "Question assertion does not match its immutable saved answer"
            raise ConflictError(msg)
        values.append(
            JsonDocument.model_validate(
                {
                    "question": question.model_dump(mode="json"),
                    "answer": answer.model_dump(mode="json"),
                }
            )
        )
    return content_digest([value.root for value in values])
