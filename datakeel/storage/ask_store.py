# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomically persist replayable question answers and shared evidence assertions."""

from sqlalchemy.orm import Session

from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import utcnow
from datakeel.core.question_models import QuestionProperties, question_revision
from datakeel.storage.ask_evidence import publish_answer_evidence
from datakeel.storage.ask_rows import AskAnswerRow, AskSessionRow
from datakeel.storage.database import Database
from datakeel.storage.evidence_store import read_assertions


def answer_in_session(session: Session, answer_id: str) -> AskAnswer:
    """Replay immutable answer details with current assertion review statuses."""
    row = session.get(AskAnswerRow, answer_id)
    if row is None:
        msg = f"Question answer not found: {answer_id}"
        raise NotFoundError(msg)
    answer = AskAnswer.model_validate(row.payload)
    observations = {item.id: item for item in read_assertions(session, answer_id)}
    return answer.model_copy(
        update={
            "assertions": tuple(
                observations[key] for key in answer.assertion_ids if key in observations
            ),
        }
    )


def get_answer(db: Database, answer_id: str) -> AskAnswer:
    """Read a previously stored answer without executing SQL or parsing the question again."""
    with db.session() as session:
        return answer_in_session(session, answer_id)


def _check_request(request: AskRequest, answer: AskAnswer) -> None:
    if (
        request.question != answer.question
        or request.reference_instant != answer.reference_instant
        or (request.session_id is not None and request.session_id != answer.session_id)
    ):
        msg = "Stored answer must match the normalized question, reference instant, and session"
        raise ValidationError(msg)
    if answer.assertion_ids or answer.assertions:
        msg = "Answer assertions must be produced by evidence storage"
        raise ValidationError(msg)
    if (
        request.metric_id is not None
        and answer.metric_card is not None
        and answer.metric_card.definition.id != request.metric_id
    ):
        msg = "Stored answer must match the explicitly selected metric"
        raise ValidationError(msg)
    _check_knowledge_request(request, answer)
    if (
        answer.profile is not None
        and answer.profile.dataset is not None
        and request.subject_id is not None
        and answer.profile.dataset.dataset_id != request.subject_id
    ):
        msg = "Stored profile answer must match the explicitly selected dataset"
        raise ValidationError(msg)


def _check_knowledge_request(request: AskRequest, answer: AskAnswer) -> None:
    knowledge = answer.knowledge
    if answer.answer_kind != "knowledge" or knowledge is None:
        return
    if (
        request.subject_id is not None
        and knowledge.subject is not None
        and request.subject_id != knowledge.subject.asset_ref.asset_id
    ):
        msg = "Stored answer must match the explicitly selected knowledge subject"
        raise ValidationError(msg)
    if (
        request.knowledge_intent is not None
        and knowledge.reason_code != "unknown_subject"
        and request.knowledge_intent != knowledge.intent
    ):
        msg = "Stored answer must match the explicitly selected knowledge intent"
        raise ValidationError(msg)


def _session(session: Session, request: AskRequest, answer: AskAnswer) -> None:
    existing = session.get(AskSessionRow, answer.session_id)
    if existing is None:
        session.add(
            AskSessionRow(
                id=answer.session_id,
                actor=request.actor,
                created_at=utcnow().isoformat(),
            )
        )
        session.flush()
    elif existing.actor != request.actor:
        msg = "Question session already belongs to a different actor"
        raise ConflictError(msg)


def _store(session: Session, request: AskRequest, answer: AskAnswer) -> AskAnswer:
    previous = session.get(AskAnswerRow, answer.id)
    if previous is not None:
        previous_answer = AskAnswer.model_validate(previous.payload)
        if AskRequest.model_validate(previous.request_payload).model_dump(
            mode="json"
        ) != request.model_dump(mode="json") or previous_answer.model_dump(
            exclude={"assertions", "assertion_ids"}
        ) != answer.model_dump(exclude={"assertions", "assertion_ids"}):
            msg = "Question answer identity already binds different immutable content"
            raise ConflictError(msg)
        return answer_in_session(session, answer.id)
    _session(session, request, answer)
    question = QuestionProperties(
        id=answer.id,
        session_id=answer.session_id,
        text=answer.question,
        content_revision=question_revision(answer.question),
        reference_instant=answer.reference_instant,
    )
    event_id, assertions = publish_answer_evidence(session, answer, question, request.actor)
    answer = answer.model_copy(
        update={
            "assertion_ids": tuple(item.id for item in assertions),
            "assertions": assertions,
        }
    )
    session.add(
        AskAnswerRow(
            id=answer.id,
            session_id=answer.session_id,
            producer_event_id=event_id,
            request_payload=request.model_dump(mode="json"),
            question_payload=question.model_dump(mode="json"),
            payload=answer.model_dump(mode="json"),
        )
    )
    session.flush()
    return answer


def store_answer_in_session(session: Session, request: AskRequest, answer: AskAnswer) -> AskAnswer:
    """Store validated immutable evidence inside the caller's write transaction."""
    request = AskRequest.model_validate(request.model_dump())
    answer = AskAnswer.model_validate(answer.model_dump())
    _check_request(request, answer)
    return _store(session, request, answer)


def store_answer(db: Database, request: AskRequest, answer: AskAnswer) -> AskAnswer:
    """Commit a session, immutable answer, and evidence event in one serialized transaction."""
    request = AskRequest.model_validate(request.model_dump())
    answer = AskAnswer.model_validate(answer.model_dump())
    _check_request(request, answer)
    with db.session() as session:
        db.lock_writes(session)
        result = _store(session, request, answer)
        session.commit()
        return result
