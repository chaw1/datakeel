# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Claim selection respects direction, reviewed links and independent source verification."""

import pytest

from datakeel.ask.knowledge_claims import document_claims
from datakeel.ask.knowledge_subjects import entity_subject
from datakeel.core.evidence_models import (
    TextSpan,
    VerificationDetail,
    VerificationIssue,
    VerificationLocation,
)
from datakeel.core.knowledge_models import KnowledgeSubject
from tests.ask.knowledge_helpers import ANCHOR, SOURCE, assertion, claim_context, source_reader


def test_source_verification_and_system_disagreement_are_independent() -> None:
    """A located quotation can need review and point to an asset absent from system lineage."""
    subject, context = claim_context()
    original = context.assertions[0]
    reviewed = original.model_copy(
        update={
            "verification": "needs_review",
            "verification_detail": VerificationDetail(
                locations=(
                    VerificationLocation(
                        source=SOURCE.asset_ref,
                        evidence=TextSpan(start=0, end=32),
                        issues=(VerificationIssue(code="tail"),),
                    ),
                ),
            ),
        }
    )
    context = context.model_copy(update={"assertions": (reviewed,)})
    claims, pending = document_claims(subject, "upstream", context, set(), source_reader)
    assert pending == 0
    claim = claims[0]
    assert claim.verification == "needs_review"
    assert claim.consistency == "not_in_system"
    assert claim.evidence[0].text == SOURCE.text[:32]
    assert claim.other_end.link_status == "candidate"
    assert claim.subject_link is not None
    assert claim.subject_link.link_status == "candidate"


@pytest.mark.parametrize("endpoint", [0, 1])
@pytest.mark.parametrize("state", ["rejected", "ambiguous"])
def test_rejected_other_link_preserves_claim_but_ambiguity_hides_it(
    endpoint: int, state: str
) -> None:
    """Subject paths need a link, while a rejected other link only removes its catalog identity."""
    subject, context = claim_context()
    links = list(context.links)
    link = links[endpoint]
    links[endpoint] = (
        link.model_copy(update={"match_kind": "ambiguous"})
        if state == "ambiguous"
        else link.model_copy(
            update={"assertion": link.assertion.model_copy(update={"status": "rejected"})}
        )
    )
    context = context.model_copy(update={"links": tuple(links)})
    claims, pending = document_claims(subject, "upstream", context, set(), source_reader)
    if endpoint == 1 and state == "rejected":
        assert len(claims) == 1
        assert claims[0].other_end.status == "not_in_catalog"
        assert claims[0].consistency == "not_in_catalog"
    else:
        assert claims == ()
    assert pending == (1 if state == "ambiguous" else 0)


def test_accepted_ownership_survives_rejected_other_link() -> None:
    """A human-confirmed relationship remains evidence after its target association is rejected."""
    _subject, context = claim_context()
    link = context.links[0]
    ownership = context.assertions[1].model_copy(update={"status": "accepted"})
    context = context.model_copy(
        update={
            "assertions": (ownership,),
            "links": (
                link.model_copy(
                    update={"assertion": link.assertion.model_copy(update={"status": "rejected"})}
                ),
            ),
        }
    )
    claims, pending = document_claims(
        entity_subject(context.entities[2]), "owned", context, set(), source_reader
    )
    assert pending == 0
    assert len(claims) == 1
    assert claims[0].relation_status == "accepted"
    assert claims[0].other_end.status == "not_in_catalog"
    assert claims[0].consistency is None


def test_accepted_ambiguous_links_are_usable_without_losing_status() -> None:
    """An explicit decision can select an ambiguous association at either endpoint."""
    subject, context = claim_context()
    links = tuple(
        link.model_copy(
            update={
                "match_kind": "ambiguous",
                "assertion": link.assertion.model_copy(update={"status": "accepted"}),
            }
        )
        for link in context.links
    )
    context = context.model_copy(
        update={
            "links": links,
            "assertions": tuple(
                item.model_copy(update={"status": "accepted"}) for item in context.assertions
            ),
        }
    )
    claims, pending = document_claims(
        subject, "upstream", context, {"source/main/orders"}, source_reader
    )
    assert pending == 0
    claim = claims[0]
    assert claim.relation_status == "accepted"
    assert claim.subject_link is not None
    assert claim.subject_link.link_status == "accepted"
    assert claim.other_end.link_status == "accepted"
    assert claim.consistency == "consistent"


def test_missing_asset_does_not_infer_alias_and_rejected_relation_disappears() -> None:
    """Accepted same_as never supplies an association or another directional relationship."""
    subject, context = claim_context()
    left, right = sorted(
        (item.asset_ref for item in context.entities[:2]), key=lambda ref: ref.asset_id
    )
    alias = assertion("alias", left, "kg.same_as", right).model_copy(update={"status": "accepted"})
    context = context.model_copy(
        update={"links": context.links[:1], "assertions": (*context.assertions, alias)}
    )
    claims, _ = document_claims(subject, "upstream", context, set(), source_reader)
    assert len(claims) == 1
    assert claims[0].consistency == "not_in_catalog"
    rejected = tuple(item.model_copy(update={"status": "rejected"}) for item in context.assertions)
    assert document_claims(
        subject,
        "related",
        context.model_copy(update={"assertions": rejected}),
        set(),
        source_reader,
    ) == ((), 0)


def test_each_intent_uses_only_its_relation_and_direction() -> None:
    """Ownership, upstream, downstream and owned assets cannot borrow unrelated one-hop facts."""
    subject, context = claim_context()
    owner = document_claims(subject, "owner", context, set(), source_reader)[0]
    assert len(owner) == 1
    assert owner[0].predicate == "owns"
    assert owner[0].consistency is None
    assert owner[0].other_end.status == "not_applicable"
    person = entity_subject(context.entities[2])
    owned = document_claims(person, "owned", context, set(), source_reader)[0]
    assert len(owned) == 1
    assert owned[0].subject_link is None
    assert owned[0].other_end.status == "linked"
    assert owned[0].consistency is None
    table = KnowledgeSubject(
        asset_ref=context.links[1].target.asset_ref, name="orders", kind="table"
    )
    assert document_claims(table, "upstream", context, set(), source_reader) == ((), 0)
    downstream = document_claims(table, "downstream", context, {"revenue"}, source_reader)[0]
    assert len(downstream) == 1
    assert downstream[0].consistency == "consistent"


def test_unlocated_evidence_stays_empty_and_source_duplicates_are_collapsed() -> None:
    """Missing evidence is not replaced with a head or tail mention from the same document."""
    subject, context = claim_context()
    item = context.assertions[0]
    missing = item.model_copy(
        update={
            "verification": "needs_review",
            "anchors": (ANCHOR, ANCHOR),
            "verification_detail": VerificationDetail(),
        }
    )
    context = context.model_copy(update={"assertions": (missing,)})
    claims, _ = document_claims(subject, "upstream", context, set(), source_reader)
    assert len(claims[0].evidence) == 1
    assert claims[0].evidence[0].text == ""
    assert claims[0].evidence[0].start is None


def test_distinct_dataset_entities_merge_only_through_the_same_asset_and_keep_sources() -> None:
    """Two linked graph identities contribute independent source receipts to one asset answer."""
    subject, context = claim_context()
    original_entity = context.entities[0]
    other_entity = original_entity.model_copy(
        update={
            "asset_ref": original_entity.asset_ref.model_copy(
                update={"asset_id": "another-dataset-metric"}
            )
        }
    )
    original_link = context.links[0]
    other_link = original_link.model_copy(
        update={
            "entity": other_entity,
            "assertion": original_link.assertion.model_copy(
                update={"id": "another-link", "subject": other_entity.asset_ref}
            ),
        }
    )
    original_claim = context.assertions[1]
    other_source = SOURCE.model_copy(
        update={
            "asset_ref": SOURCE.asset_ref.model_copy(update={"asset_id": "another-document"}),
            "filename": "other-notes.txt",
        }
    )
    other_claim = original_claim.model_copy(
        update={
            "id": "another-owner",
            "object": other_entity.asset_ref,
            "anchors": (ANCHOR.model_copy(update={"asset_ref": other_source.asset_ref}),),
        }
    )
    combined = context.model_copy(
        update={
            "entities": (*context.entities, other_entity),
            "links": (*context.links, other_link),
            "assertions": (original_claim, other_claim),
        }
    )
    claims, pending = document_claims(
        subject,
        "owner",
        combined,
        set(),
        lambda anchor: SOURCE if anchor.asset_ref.asset_id == "document" else other_source,
    )
    assert pending == 0
    assert len(claims) == 2
    assert {claim.evidence[0].document for claim in claims} == {
        "synthetic-notes.txt",
        "other-notes.txt",
    }
    assert {
        claim.subject_link.entity.asset_ref.asset_id for claim in claims if claim.subject_link
    } == {
        "metric-entity",
        "another-dataset-metric",
    }
