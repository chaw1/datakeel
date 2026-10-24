# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve partial-source evidence and generate explicit nontransitive alias pairs."""

from datakeel.core.evidence_models import VerificationDetail
from datakeel.core.kg_product import ProductExtraction
from datakeel.kg.aliases import same_as_drafts
from datakeel.kg.identity import merge_drafts
from datakeel.kg.loader import get_schema
from datakeel.kg.retention import preserve_unselected
from tests.kg.helpers import assertions_for, graph_product


def test_unselected_document_retains_its_relation_and_source_checks() -> None:
    """Replacing source A cannot erase a triple still supported by source B."""
    first, source = graph_product(file_id="first")
    second, _ = graph_product(file_id="second")
    merged = ProductExtraction(drafts=merge_drafts((*first.drafts, *second.drafts)))
    kept = preserve_unselected(assertions_for(merged), {"first"})
    relation = next(item for item in kept if item.predicate == "kg.uses")
    assert {anchor.asset_ref.asset_id for anchor in relation.anchors} == {"second"}
    assert relation.verification == "verified"
    assert relation.verification_detail is not None
    assert len(relation.verification_detail.locations) == 1
    assert preserve_unselected(assertions_for(first), {source.file.asset_id}) == ()
    assert len(preserve_unselected(assertions_for(first), set())) == len(first.drafts)


def test_retention_ignores_non_graph_and_marks_missing_location_metadata() -> None:
    """Incomplete historical check metadata never leaves a misleading verified highlight."""
    first, _ = graph_product(file_id="first")
    second, _ = graph_product(file_id="second")
    merged = ProductExtraction(drafts=merge_drafts((*first.drafts, *second.drafts)))
    relation = next(item for item in assertions_for(merged) if item.predicate == "kg.uses")
    missing = relation.model_copy(update={"verification_detail": VerificationDetail()})
    retained = preserve_unselected((missing,), {"first"})[0]
    assert retained.verification == "needs_review"
    assert retained.verification_detail is not None
    assert retained.verification_detail.head is None
    legacy = relation.model_copy(update={"predicate": "near_duplicate_of"})
    assert preserve_unselected((legacy,), set()) == ()


def test_alias_candidates_are_cross_document_canonical_review_pairs() -> None:
    """Name containment yields a reviewable pair, with no automatic merge or duplicate pair."""
    left, source = graph_product("Acme", "left")
    right, _ = graph_product("Acme Group", "right")
    entities, drafts = (*left.entities, *right.entities), (*left.drafts, *right.drafts)
    pairs = same_as_drafts(entities, drafts, get_schema(), source.extractor)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.verification == "needs_review"
    assert pair.verification_detail is not None
    assert pair.verification_detail.issues[0].code == "evidence"
    assert pair.subject.asset_id < pair.object.asset_id
    assert same_as_drafts(entities, (*drafts, pair), get_schema(), source.extractor) == ()
    kept = preserve_unselected(assertions_for(ProductExtraction(drafts=pairs)), {"left"})
    assert kept[0].verification == "needs_review"
    assert same_as_drafts(entities, (), get_schema(), source.extractor) == ()


def test_aliases_require_same_type_and_distinct_document_sources() -> None:
    """Names alone cannot invent cross-category or same-document alias evidence."""
    left, source = graph_product("Acme", "same")
    right, _ = graph_product("Acme Group", "same")
    assert (
        same_as_drafts(
            (*left.entities, *right.entities),
            (*left.drafts, *right.drafts),
            get_schema(),
            source.extractor,
        )
        == ()
    )
    right_entities = tuple(
        entity.model_copy(update={"type": "person"}) for entity in right.entities
    )
    assert (
        same_as_drafts(
            (*left.entities, *right_entities),
            (*left.drafts, *right.drafts),
            get_schema(),
            source.extractor,
        )
        == ()
    )


def test_schema_aliases_can_relate_names_without_substring_overlap() -> None:
    """Explicit aliases are eligible without borrowing benchmark-only label tables."""
    left, source = graph_product("Acme", "left")
    right, _ = graph_product("Example Team", "right")
    schema = get_schema()
    schema = schema.model_copy(
        update={
            "entity_types": tuple(
                item.model_copy(update={"aliases": {"Acme": ("Example Team",)}})
                if item.name == "organization"
                else item
                for item in schema.entity_types
            )
        }
    )
    assert (
        len(
            same_as_drafts(
                (*left.entities, *right.entities),
                (*left.drafts, *right.drafts),
                schema,
                source.extractor,
            )
        )
        == 1
    )


def test_merged_verification_payload_is_independent_of_input_order() -> None:
    """Equal immutable assertion IDs also have equal source-check metadata."""
    first, _ = graph_product(file_id="first")
    second, _ = graph_product(file_id="second")
    assert merge_drafts((*first.drafts, *second.drafts)) == merge_drafts(
        (*second.drafts, *first.drafts)
    )


def test_removed_schema_type_does_not_break_retained_document_aliases() -> None:
    """Partial extraction may preserve old entity types absent from the new vocabulary."""
    left, source = graph_product("Acme", "left")
    right, _ = graph_product("Example Team", "right")
    schema = get_schema().model_copy(update={"entity_types": ()})
    assert (
        same_as_drafts(
            (*left.entities, *right.entities),
            (*left.drafts, *right.drafts),
            schema,
            source.extractor,
        )
        == ()
    )
