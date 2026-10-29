# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Product-state count labels follow typed keys, localized labels and English inflections."""

from datetime import UTC, datetime
from typing import get_args

import pytest

from datakeel.core.datasheet_models import (
    DatasheetFact,
    DatasheetSection,
    DatasheetSentence,
)
from datakeel.core.evidence_models import AssertionStatus, Verification
from datakeel.datasheets.number_labels import key_labels
from datakeel.datasheets.numeric import numeric_issues
from datakeel.datasheets.validation import validate_sections
from datakeel.datasheets.vocabulary import EVIDENCE_STATE_LABELS


def _fact(field: str, value: dict[str, int]) -> DatasheetFact:
    return DatasheetFact(
        id="f1",
        chapter="composition",
        source_type="version",
        source_id="v1",
        field=field,
        value=value,
        recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
    )


def test_state_vocabulary_matches_product_types() -> None:
    """Every real product state has presentation labels, with no invented pending state."""
    assert set(EVIDENCE_STATE_LABELS) == set(get_args(AssertionStatus)) | set(
        get_args(Verification)
    )
    assert key_labels("pending") == ("pending",)


def test_candidate_labels_derive_from_product_states() -> None:
    """The actual candidate state supports its plural and Chinese display wording."""
    facts = (_fact("assertions.status_counts", {"accepted": 73, "candidate": 11}),)
    assert numeric_issues("11 assertions are candidates.", facts) == ()
    assert numeric_issues("11 条断言为候选。", facts) == ()
    assert numeric_issues("73 assertions are candidates.", facts) == ("unsupported_number",)


def test_review_labels_derive_english_inflections() -> None:
    """Need and needs share the product's needs_review key without borrowing verified counts."""
    facts = (_fact("assertions.verification_counts", {"verified": 29, "needs_review": 7}),)
    assert numeric_issues("7 assertions need review.", facts) == ()
    assert numeric_issues("7 assertions needs review.", facts) == ()
    assert numeric_issues("29 assertions need review.", facts) == ("unsupported_number",)


def test_state_predicates_keep_the_counted_assertion_object() -> None:
    """Known predicates follow a count noun; unrelated trailing nouns remain unsupported."""
    facts = (_fact("assertions.verification_counts", {"verified": 29, "needs_review": 7}),)
    assert numeric_issues("7 assertions still need review.", facts) == ()
    assert numeric_issues("7 条断言待复核。", facts) == ()
    assert numeric_issues("Needs review: 7 reviewers.", facts) == ("unsupported_number",)
    assert numeric_issues("7 assertions still need review contributors.", facts) == (
        "unsupported_number",
    )


@pytest.mark.parametrize(
    "text",
    ["9 assertions still need review.", "9 条断言待复核。"],
)
def test_localized_review_state_survives_complete_citation_validation(
    text: str,
) -> None:
    """The retained product wording also passes the independent content-word validator."""
    fact = _fact("assertions.verification_counts", {"verified": 52, "needs_review": 9})
    section = DatasheetSection(
        key="composition",
        title="Composition",
        sentences=(DatasheetSentence(text=text, fact_ids=(fact.id,)),),
    )
    result = validate_sections((section,), (fact,), "zh")
    assert not result.dropped_sentences


def test_localized_candidate_survives_complete_citation_validation() -> None:
    """Both original candidate examples pass word validation as well as number binding."""
    fact = _fact("assertions.status_counts", {"accepted": 1200, "candidate": 85})
    for text in (
        "Reviewers accepted 1200 assertions; 85 are candidates.",
        "85 条证据断言仍为候选。",
    ):
        section = DatasheetSection(
            key="composition",
            title="Composition",
            sentences=(DatasheetSentence(text=text, fact_ids=(fact.id,)),),
        )
        assert not validate_sections((section,), (fact,), "zh").dropped_sentences
