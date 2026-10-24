# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict versioned selectors, presence semantics, and replayable cache identities."""

import pytest
from pydantic import ValidationError

from datakeel.core.evidence_cache import (
    EvidenceCacheEntry,
    EvidenceCacheKey,
    EvidenceInput,
    KnowledgeBundle,
)
from datakeel.core.models import AssetRef
from datakeel.evidence import cache, models
from datakeel.evidence.models import (
    Assertion,
    EvidenceAnchor,
    EvidenceValue,
    ImageRegion,
    TextSpan,
    Whole,
)
from datakeel.evidence.registry import PREDICATES, predicate
from tests.evidence.helpers import extraction_event


def test_selector_valid_intervals_preserve_versioned_content() -> None:
    """Accept exact typed selectors and immutable, versioned evidence anchors."""
    ref = AssetRef(asset_id="caption", version="v1")
    for selector in (
        Whole(),
        TextSpan(start=1, end=4),
        ImageRegion(bbox=(0, 1, 5, 4), width=10, height=10),
    ):
        anchor = EvidenceAnchor(asset_ref=ref, content_revision="a" * 64, selector=selector)
        assert EvidenceAnchor.model_validate_json(anchor.model_dump_json()) == anchor
        with pytest.raises(ValidationError, match="frozen"):
            anchor.content_revision = "b" * 64


@pytest.mark.parametrize(
    "selector",
    [
        {"type": "text_span", "start": 4, "end": 4},
        {"type": "time_range", "start_ms": 4, "end_ms": 3},
        {"type": "image_region", "bbox": [0, 0, 11, 2], "width": 10, "height": 10},
        {"type": "image_region", "bbox": [0, 0, float("nan"), 2], "width": 10, "height": 10},
    ],
)
def test_selector_invalid_coordinates_fail_validation(selector: dict[str, object]) -> None:
    """Reject empty, reversed, nonfinite, and out-of-bounds regions."""
    with pytest.raises(ValidationError):
        EvidenceAnchor.model_validate(
            {
                "asset_ref": {"asset_id": "a", "version": "v1"},
                "content_revision": "a" * 64,
                "selector": selector,
            }
        )


def test_anchor_missing_version_or_content_identity_is_rejected() -> None:
    """Disallow evidence pointing only at a mutable asset alias or path."""
    with pytest.raises(ValidationError, match="version"):
        EvidenceAnchor(asset_ref=AssetRef(asset_id="a"), content_revision="a" * 64)
    with pytest.raises(ValidationError, match="pattern"):
        EvidenceAnchor(asset_ref=AssetRef(asset_id="a", version="v"), content_revision="path")


def test_assertion_three_states_and_predicate_registry_are_explicit() -> None:
    """Retain unknown separately from measured absence and disallow transitive duplicates."""
    original = KnowledgeBundle.model_validate(
        extraction_event().params["knowledge_bundle"]
    ).assertions[0]
    for state in ("present", "absent", "unknown"):
        assertion = Assertion.model_validate(
            {**original.model_dump(), "object": {"concept": "person", "value": state}}
        )
        assert isinstance(assertion.object, EvidenceValue)
        assert assertion.object.value == state
    assert tuple(item.id for item in PREDICATES) == (
        "mentions",
        "annotated_as",
        "label_gap",
        "near_duplicate_of",
        "corrupt",
        "ask.answers_with",
        "ask.matched_term",
        "ask.unanswerable",
        "link.maps_to",
        "ask.cites_asset",
        "ask.cites_assertion",
        "ask.knowledge_unresolved",
    )
    assert predicate("near_duplicate_of").symmetric
    assert not predicate("near_duplicate_of").transitive
    assert not predicate("mentions").symmetric
    assert models.Assertion is Assertion
    assert cache.EvidenceCacheKey is EvidenceCacheKey


def test_assertion_invalid_semantics_and_timestamps_are_rejected() -> None:
    """Require measured distinct duplicate pairs and three-state existence values."""
    original = KnowledgeBundle.model_validate(
        extraction_event().params["knowledge_bundle"]
    ).assertions[0]
    invalid = [
        {"object": original.subject},
        {"created_at": "2026-01-01T00:00:00"},
        {"decided_at": "2026-01-01T00:00:00"},
        {"predicate": "near_duplicate_of"},
        {"predicate": "near_duplicate_of", "object": original.subject, "distance": 0},
    ]
    for update in invalid:
        with pytest.raises(ValidationError):
            Assertion.model_validate({**original.model_dump(), **update})
    duplicate = Assertion.model_validate(
        {
            **original.model_dump(),
            "predicate": "near_duplicate_of",
            "distance": 2,
            "object": {"asset_id": "other", "asset_type": "file", "version": "v1"},
        }
    )
    assert duplicate.distance == 2


def test_cache_keys_include_all_inputs_selectors_and_extractor_versions() -> None:
    """Detect dependency changes while ignoring paths, identities, and input order."""
    bundle = KnowledgeBundle.model_validate(extraction_event().params["knowledge_bundle"])
    key = bundle.cache_entries[0].key
    caption = EvidenceInput(role="caption", content_revision="b" * 64)
    pair = key.model_copy(update={"inputs": (*key.inputs, caption)})
    assert (
        pair.digest() == pair.model_copy(update={"inputs": tuple(reversed(pair.inputs))}).digest()
    )
    assert pair.digest() != key.digest()
    assert (
        pair.digest()
        != pair.model_copy(
            update={
                "inputs": (
                    *key.inputs,
                    caption.model_copy(update={"selector": TextSpan(start=0, end=2)}),
                )
            }
        ).digest()
    )
    assert (
        pair.digest()
        != pair.model_copy(
            update={"extractor": key.extractor.model_copy(update={"version": "2"})}
        ).digest()
    )
    renamed = bundle.cache_entries[0].subject.model_copy(update={"display_name": "moved.png"})
    assert (
        EvidenceCacheEntry(subject=renamed, key=key, assertion_ids=()).slot
        == bundle.cache_entries[0].slot
    )


def test_bundle_rejects_cross_run_duplicate_and_foreign_cache_references() -> None:
    """Keep cached observation identities bound to the exact producing run."""
    bundle = KnowledgeBundle.model_validate(extraction_event().params["knowledge_bundle"])
    for update in (
        {"run_id": "wrong"},
        {"assertions": (*bundle.assertions, *bundle.assertions)},
        {
            "cache_entries": (
                bundle.cache_entries[0].model_copy(update={"assertion_ids": ("unknown",)}),
            )
        },
    ):
        with pytest.raises(ValidationError):
            KnowledgeBundle.model_validate({**bundle.model_dump(), **update})


def test_concept_presence_cannot_invent_absence_and_requires_concept_id() -> None:
    """Require canonical concepts and reserve absent for direct measured corruption."""
    original = KnowledgeBundle.model_validate(
        extraction_event().params["knowledge_bundle"]
    ).assertions[0]
    for predicate_id in ("mentions", "annotated_as", "label_gap"):
        for value in ({"concept": "person", "value": "absent"}, {"value": "unknown"}):
            with pytest.raises(ValidationError):
                Assertion.model_validate(
                    {**original.model_dump(), "predicate": predicate_id, "object": value}
                )
    with pytest.raises(ValidationError, match="ordered"):
        Assertion.model_validate(
            {
                **original.model_dump(),
                "predicate": "near_duplicate_of",
                "distance": 1,
                "object": {"asset_id": "a-first", "asset_type": "file", "version": "v1"},
            }
        )


def test_cache_identity_changes_for_contracts_and_subject_versions() -> None:
    """Include both source contracts and keep cached evidence anchored to its source version."""
    entry = KnowledgeBundle.model_validate(
        extraction_event().params["knowledge_bundle"]
    ).cache_entries[0]
    assert entry.key.digest() != entry.key.model_copy(update={"lexicon_hash": "e" * 64}).digest()
    assert (
        entry.key.digest()
        != entry.key.model_copy(update={"near_duplicate_hash": "f" * 64}).digest()
    )
    assert (
        entry.slot
        != entry.model_copy(
            update={"subject": entry.subject.model_copy(update={"version": "new"})}
        ).slot
    )
    with pytest.raises(ValidationError, match="version"):
        EvidenceCacheEntry(
            subject=AssetRef(asset_id="unversioned"), key=entry.key, assertion_ids=()
        )


@pytest.mark.parametrize(
    ("predicate_id", "subject_kind", "object_kind"),
    [
        ("link.maps_to", "kg_entity", "table"),
        ("link.maps_to", "kg_entity", "metric"),
        ("ask.cites_asset", "question", "metric"),
        ("ask.cites_asset", "question", "table"),
        ("ask.cites_asset", "question", "owner"),
        ("ask.cites_asset", "question", "kg_entity"),
        ("ask.cites_assertion", "question", "assertion"),
    ],
)
def test_link_and_knowledge_predicates_reject_unrelated_subjects_and_objects(
    predicate_id: str,
    subject_kind: str,
    object_kind: str,
) -> None:
    """New citation predicates preserve explicit endpoint constraints at the assertion boundary."""
    original = KnowledgeBundle.model_validate(
        extraction_event().params["knowledge_bundle"]
    ).assertions[0]
    payload = {
        **original.model_dump(),
        "predicate": predicate_id,
        "subject": AssetRef(asset_type=subject_kind, asset_id="subject", version="subject"),
        "object": AssetRef(asset_type=object_kind, asset_id="target", version="target"),
    }
    assert Assertion.model_validate(payload).predicate == predicate_id
    with pytest.raises(ValidationError, match=r"requires a .* subject"):
        Assertion.model_validate({**payload, "subject": original.subject})
    with pytest.raises(ValidationError, match="requires object types"):
        Assertion.model_validate(
            {**payload, "object": AssetRef(asset_type="file", asset_id="unrelated", version="1")}
        )
