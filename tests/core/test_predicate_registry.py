# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Registered object/value predicates retain legacy semantics and question provenance."""

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from datakeel.core.evidence_models import Assertion, EvidenceAnchor, EvidenceValue, ExtractorRef
from datakeel.core.models import AssetRef
from datakeel.core.object_kinds import object_property_model
from datakeel.core.predicate_registry import (
    Predicate,
    predicate,
    register_predicate,
    registered_predicates,
)
from datakeel.core.question_models import QuestionProperties, question_revision
from datakeel.ontology.models import ObjectSet


def _assertion(kind: str, observed: AssetRef | EvidenceValue) -> Assertion:
    question = AssetRef(asset_type="question", asset_id="question", version="question")
    return Assertion(
        subject=question,
        predicate=kind,
        object=observed,
        anchors=(EvidenceAnchor(asset_ref=question, content_revision="a" * 64),),
        extractor=ExtractorRef(id="evidence.ask", version="1.0"),
        producer_event_id="event",
        run_id="question",
    )


def test_predicate_registration_validates_every_evidence_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dynamically declared vocabulary works while unknown and conflicting ids fail."""
    monkeypatch.setattr(
        "datakeel.core.predicate_registry._PREDICATES",
        {item.id: item for item in registered_predicates()},
    )
    definition = Predicate(id="fixture.measured", description="Fixture measured concept")
    register_predicate(definition)
    register_predicate(definition)
    assert predicate(definition.id) == definition
    assert _assertion(definition.id, EvidenceValue(concept="fixture", value="present"))
    with pytest.raises(ValueError, match="different declaration"):
        register_predicate(definition.model_copy(update={"description": "Other"}))
    with pytest.raises(ValidationError, match="Unregistered evidence predicate"):
        _assertion("unknown.predicate", EvidenceValue(concept="fixture", value="present"))


@pytest.mark.parametrize(
    ("kind", "observed"),
    [
        ("ask.answers_with", AssetRef(asset_type="metric", asset_id="revenue", version="1")),
        ("ask.matched_term", AssetRef(asset_type="term", asset_id="term/Revenue", version="2")),
        ("ask.unanswerable", EvidenceValue(concept="metric", value="unknown")),
    ],
)
def test_question_predicates_accept_declared_object_types(
    kind: str,
    observed: AssetRef | EvidenceValue,
) -> None:
    """Each namespaced predicate admits exactly its declared kind of evidence."""
    assert _assertion(kind, observed).object == observed


@pytest.mark.parametrize(
    ("kind", "observed"),
    [
        ("ask.answers_with", EvidenceValue(concept="metric", value="present")),
        ("ask.answers_with", AssetRef(asset_type="term", asset_id="term/Revenue", version="1")),
        ("ask.answers_with", AssetRef(asset_type="metric", asset_id="revenue")),
        ("ask.matched_term", AssetRef(asset_type="metric", asset_id="revenue", version="1")),
        ("ask.unanswerable", EvidenceValue(concept="metric", value="present")),
        ("ask.unanswerable", EvidenceValue(concept="revenue", value="unknown")),
    ],
)
def test_question_predicates_reject_mismatched_or_unversioned_objects(
    kind: str,
    observed: AssetRef | EvidenceValue,
) -> None:
    """Reject wrong reference kinds and fabricated positive unanswerable facts."""
    with pytest.raises(ValidationError):
        _assertion(kind, observed)


@pytest.mark.parametrize(
    "subject",
    [
        AssetRef(asset_type="file", asset_id="question", version="question"),
        AssetRef(asset_type="question", asset_id="question", version="other"),
    ],
)
def test_question_assertions_require_answer_identity_as_subject_version(subject: AssetRef) -> None:
    """Never attach ask facts to unversioned or unrelated asset identities."""
    original = _assertion("ask.unanswerable", EvidenceValue(concept="metric", value="unknown"))
    with pytest.raises(ValidationError):
        Assertion.model_validate({**original.model_dump(), "subject": subject})


def test_question_kind_is_registered_before_storage_import_and_is_not_selectable() -> None:
    """Expose question schemas deterministically without broadening frozen file selection."""
    assert object_property_model("question") is QuestionProperties
    with pytest.raises(ValidationError, match="frozen asset selections"):
        ObjectSet(object_type="question")


def test_question_properties_bind_nfc_text_to_reproducible_revision() -> None:
    """Equivalent composed text hashes identically, but stored text must already be NFC."""
    text = "é零售额"
    assert question_revision("e\u0301零售额") == hashlib.sha256(text.encode()).hexdigest()
    question = QuestionProperties(
        id="answer",
        session_id="session",
        text=text,
        content_revision=question_revision(text),
        reference_instant=datetime(2026, 10, 1, tzinfo=UTC),
    )
    assert question.asset_ref() == AssetRef(
        asset_type="question", asset_id="answer", version="answer"
    )
    for update in ({"text": "e\u0301零售额"}, {"content_revision": "a" * 64}):
        with pytest.raises(ValidationError):
            QuestionProperties.model_validate({**question.model_dump(), **update})
