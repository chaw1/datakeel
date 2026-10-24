# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomic question persistence, reviewed replay, and unified evidence reconstruction."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.errors import ConflictError, ExecutionError, NotFoundError, ValidationError
from datakeel.core.evidence_models import (
    Assertion,
    AssertionDecisionRequest,
    EvidenceValue,
    TextSpan,
    Whole,
)
from datakeel.core.knowledge_models import KnowledgeAnswer, KnowledgeSubject
from datakeel.core.models import AssetRef
from datakeel.core.question_models import QuestionProperties, question_revision
from datakeel.storage.ask_evidence import publish_answer_evidence
from datakeel.storage.ask_rows import AskAnswerRow, AskSessionRow
from datakeel.storage.ask_store import get_answer, store_answer
from datakeel.storage.database import Database, EventRow
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.evidence_projection import projection_hash, rebuild_evidence
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import list_assertions, record_extraction
from datakeel.storage.metric_store import update_metric_in_session
from tests.evidence.helpers import extraction_event
from tests.storage.ask_helpers import answer_case, refusal_case


def _counts(db: Database) -> tuple[int, ...]:
    with db.session() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model)) or 0
            for model in (AskSessionRow, AskAnswerRow, EventRow, AssertionRow)
        )


def test_answer_persists_sql_parameters_and_versioned_question_facts(db: Database) -> None:
    """Replay the exact result and anchors without running a second source query."""
    request, draft = answer_case(db)
    saved = store_answer(db, request, draft)
    assert get_answer(db, saved.id) == saved
    assert {item.predicate for item in saved.assertions} == {"ask.answers_with", "ask.matched_term"}
    assert all(
        item.subject.asset_type == "question" and item.subject.version == saved.id
        for item in saved.assertions
    )
    for assertion in saved.assertions:
        assert assertion.anchors[0].content_revision == question_revision(request.question)
        assert isinstance(assertion.anchors[0].selector, TextSpan)
    with db.session() as session:
        row = session.get(AskAnswerRow, saved.id)
        assert row is not None
        assert row.payload["sql"] == saved.sql.model_dump(mode="json") if saved.sql else False
        assert row.payload["result"] == {"columns": ["value"], "rows": [[30]], "truncated": False}


def test_refusal_persists_unknown_metric_with_whole_question_anchor(db: Database) -> None:
    """Unsupported questions publish unknown facts without inventing a numerical result."""
    request, draft = refusal_case()
    saved = store_answer(db, request, draft)
    assert len(saved.assertions) == 1
    assertion = saved.assertions[0]
    assert assertion.object == EvidenceValue(concept="metric", value="unknown")
    assert isinstance(assertion.anchors[0].selector, Whole)
    assert get_answer(db, saved.id).result is None


def test_storage_retries_are_event_free_and_conflicting_content_is_rejected(db: Database) -> None:
    """An answer id binds one immutable request and outcome across repeated publication."""
    request, draft = answer_case(db)
    first = store_answer(db, request, draft)
    counts = _counts(db)
    assert store_answer(db, request, draft) == first
    assert _counts(db) == counts
    with pytest.raises(ConflictError, match="different immutable content"):
        store_answer(db, request, draft.model_copy(update={"message": "Changed"}))
    with pytest.raises(NotFoundError, match="not found"):
        get_answer(db, "unknown")


def test_storage_retry_when_old_request_has_no_metric_pin_keeps_original_answer(
    db: Database,
) -> None:
    """The new optional request field does not invalidate already persisted retry identities."""
    request, draft = answer_case(db)
    first = store_answer(db, request, draft)
    with db.session() as session:
        row = session.get(AskAnswerRow, first.id)
        assert row is not None
        row.request_payload = {
            key: value for key, value in row.request_payload.items() if key != "metric_id"
        }
        session.commit()
    counts = _counts(db)
    assert store_answer(db, request, draft) == first
    assert _counts(db) == counts


def test_storage_when_metric_pin_conflicts_with_answer_rejects_before_publication(
    db: Database,
) -> None:
    """The explicit selection becomes part of the immutable request-answer binding."""
    request, draft = answer_case(db)
    with pytest.raises(ValidationError, match="explicitly selected metric"):
        store_answer(db, request.model_copy(update={"metric_id": "different"}), draft)
    assert _counts(db)[:2] == (0, 0)


def _knowledge_case() -> tuple[AskRequest, AskAnswer]:
    request, draft = refusal_case()
    subject = KnowledgeSubject(
        asset_ref=AssetRef(asset_type="metric", asset_id="revenue", version="1"),
        name="Revenue",
        kind="metric",
    )
    knowledge = KnowledgeAnswer(intent="upstream", subject=subject, reason_code="no_knowledge")
    return request, draft.model_copy(update={"answer_kind": "knowledge", "knowledge": knowledge})


@pytest.mark.parametrize(
    ("selection", "error"),
    [
        ({"subject_id": "another-metric"}, "selected knowledge subject"),
        ({"knowledge_intent": "owner"}, "selected knowledge intent"),
    ],
)
def test_knowledge_selection_must_match_before_any_publication(
    db: Database, selection: dict[str, str], error: str
) -> None:
    """A forged selected subject or intent cannot be saved as the user's requested answer."""
    request, draft = _knowledge_case()
    with pytest.raises(ValidationError, match=error):
        store_answer(db, request.model_copy(update=selection), draft)
    assert _counts(db) == (0, 0, 0, 0)


def test_matching_knowledge_selection_round_trips_in_the_saved_request(db: Database) -> None:
    """Resolved no-fact replies preserve a valid subject and intent selection on replay."""
    request, draft = _knowledge_case()
    request = request.model_copy(update={"subject_id": "revenue", "knowledge_intent": "upstream"})
    saved = store_answer(db, request, draft)
    assert get_answer(db, saved.id) == saved
    with db.session() as session:
        row = session.get(AskAnswerRow, saved.id)
        assert row is not None
        assert row.request_payload["subject_id"] == "revenue"
        assert row.request_payload["knowledge_intent"] == "upstream"


def test_unknown_knowledge_subject_can_refuse_an_invalid_pinned_selection(db: Database) -> None:
    """A missing selected subject remains a refusal rather than a fabricated resolved subject."""
    request, draft = _knowledge_case()
    request = request.model_copy(update={"subject_id": "missing", "knowledge_intent": "owner"})
    draft = draft.model_copy(
        update={"knowledge": KnowledgeAnswer(intent="related", reason_code="unknown_subject")}
    )
    saved = store_answer(db, request, draft)
    assert saved.knowledge is not None
    assert saved.knowledge.subject is None
    assert saved.knowledge.reason_code == "unknown_subject"


def test_metric_answers_ignore_knowledge_only_selection_fields(db: Database) -> None:
    """Knowledge pins cannot redirect or invalidate an otherwise valid numerical request."""
    request, draft = answer_case(db)
    request = request.model_copy(update={"subject_id": "unused", "knowledge_intent": "owner"})
    saved = store_answer(db, request, draft)
    assert saved.result == draft.result
    assert saved.answer_kind == "metric"


def test_answer_rejects_request_mismatch_and_caller_supplied_assertions(db: Database) -> None:
    """Only storage can bind provenance, and answer/request identities must agree."""
    request, draft = refusal_case()
    with pytest.raises(ValidationError, match="must match"):
        store_answer(db, request.model_copy(update={"session_id": "other"}), draft)
    saved = store_answer(db, request, draft)
    with pytest.raises(ValidationError, match="produced by evidence storage"):
        store_answer(db, request, saved)


def test_session_can_hold_multiple_turns_but_cannot_change_actor(db: Database) -> None:
    """Keep turn grouping and actor attribution persistent instead of process-local."""
    request, draft = refusal_case()
    store_answer(db, request, draft)
    next_request = request.model_copy(update={"session_id": draft.session_id})
    store_answer(db, next_request, draft.model_copy(update={"id": "next-answer"}))
    assert _counts(db)[:2] == (1, 2)
    with pytest.raises(ConflictError, match="different actor"):
        store_answer(
            db,
            next_request.model_copy(update={"actor": "other"}),
            draft.model_copy(update={"id": "third-answer"}),
        )


def test_question_metric_and_term_references_must_still_be_registered(db: Database) -> None:
    """Reject fabricated glossary ids and answers compiled against stale definitions."""
    request, draft = answer_case(db)
    missing = draft.matches[0].model_copy(update={"term_id": "term/missing"})
    with pytest.raises(ValidationError, match="unregistered term"):
        store_answer(db, request, draft.model_copy(update={"matches": (missing,)}))
    assert _counts(db)[:2] == (0, 0)
    assert draft.metric_card is not None
    with db.session() as session:
        update_metric_in_session(
            session, draft.metric_card.definition.model_copy(update={"owner": "New"})
        )
        session.commit()
    with pytest.raises(ConflictError, match="changed or disappeared"):
        store_answer(db, request, draft)


def test_duplicate_text_matches_produce_one_assertion_per_anchor(db: Database) -> None:
    """Overlapping name/glossary discovery does not duplicate the same semantic fact."""
    request, draft = answer_case(db)
    saved = store_answer(db, request, draft.model_copy(update={"matches": draft.matches * 2}))
    assert len(saved.assertions) == 2
    another = draft.model_copy(
        update={
            "id": "without-term",
            "matches": (draft.matches[0].model_copy(update={"term_id": None}),),
        }
    )
    assert len(store_answer(db, request, another).assertions) == 1


def test_question_and_legacy_facts_share_rebuild_and_review_overlay(db: Database) -> None:
    """One projector restores both predicate namespaces and the original audit decisions."""
    request, draft = answer_case(db)
    saved = store_answer(db, request, draft)
    record_extraction(db, extraction_event())
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=saved.assertion_ids,
            status="accepted",
            actor="reviewer",
            idempotency_key="review",
        ),
    )
    before = projection_hash(db)
    rebuilt = rebuild_evidence(db, before)
    assert rebuilt.matches
    assert rebuilt.assertions == 3
    assert projection_hash(db) == before
    assert all(item.status == "accepted" for item in get_answer(db, saved.id).assertions)
    assert {item.predicate for item in list_assertions(db)} == {
        "corrupt",
        "ask.answers_with",
        "ask.matched_term",
    }
    with db.session() as session:
        row = session.get(AskAnswerRow, saved.id)
        assert row is not None
        assert {item["status"] for item in row.payload["assertions"]} == {"candidate"}


def test_answer_and_assertions_rollback_together_after_publication_failure(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No partial answer/session/event survives an interrupted completion transaction."""
    request, draft = refusal_case()
    publisher = publish_answer_evidence

    def fail_after_event(
        session: Session,
        answer: AskAnswer,
        question: QuestionProperties,
        actor: str,
    ) -> tuple[str, tuple[Assertion, ...]]:
        publisher(session, answer, question, actor)
        msg = "fixture failure after evidence publication"
        raise ExecutionError(msg)

    monkeypatch.setattr("datakeel.storage.ask_store.publish_answer_evidence", fail_after_event)
    with pytest.raises(ExecutionError, match="after evidence"):
        store_answer(db, request, draft)
    assert _counts(db) == (0, 0, 0, 0)
