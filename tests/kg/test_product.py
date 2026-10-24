# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise verification, endpoint resolution and deterministic assertion content."""

import hashlib

import pytest

from datakeel.core.evidence_models import ExtractorRef, TextSpan, Whole
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation, KGSchema
from datakeel.core.kg_models import RawExtraction
from datakeel.core.kg_product import KGSource, ProductExtraction
from datakeel.core.models import AssetRef
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.identity import assertion_identity, entity_asset_ref, merge_drafts
from datakeel.kg.loader import get_schema
from datakeel.kg.text import decode_text, normalize_name
from datakeel.kg.verification import entity_spans, find_spans, nearest_span


def _source(text: str, file_id: str = "document") -> KGSource:
    return KGSource(
        dataset_id="dataset",
        dataset_version_id="version",
        file=AssetRef(asset_type="file", asset_id=file_id, version="version"),
        text=text,
        content_revision=hashlib.sha256(text.encode()).hexdigest(),
        extractor=ExtractorRef(id="replay", version="model-v1"),
    )


def _raw(
    *,
    head: str = "Acme",
    tail: str = "Widget",
    predicate: str = "uses",
    evidence: str = "Acme uses Widget.",
) -> RawExtraction:
    return RawExtraction(
        entities=(
            ExtractedEntity(name=head, type="organization"),
            ExtractedEntity(name=tail, type="system"),
        ),
        relations=(ExtractedRelation(head=head, relation=predicate, tail=tail, evidence=evidence),),
    )


def _relations(product: ProductExtraction) -> list[str | None]:
    return [draft.verification for draft in product.drafts if draft.predicate != "kg.mentions"]


def test_hallucinated_entity_with_valid_evidence_needs_review() -> None:
    """An exact quotation cannot verify an entity absent from the entire document."""
    product = assemble_extraction(_raw(tail="Vivo"), get_schema(), _source("Acme uses Widget."))
    relation = next(draft for draft in product.drafts if draft.predicate == "kg.uses")
    assert relation.verification == "needs_review"
    assert relation.verification_detail is not None
    assert [issue.code for issue in relation.verification_detail.issues] == ["tail"]
    assert relation.verification_detail.evidence == TextSpan(start=0, end=17)
    missing_mention = next(
        draft
        for draft in product.drafts
        if draft.subject.display_name == "vivo" and draft.predicate == "kg.mentions"
    )
    assert missing_mention.verification == "needs_review"


def test_paraphrased_evidence_remains_candidate_with_whole_anchor() -> None:
    """Unlocatable evidence produces a reviewable draft rather than a silent drop."""
    product = assemble_extraction(
        _raw(evidence="Acme adopted Widget"), get_schema(), _source("Acme uses Widget.")
    )
    relation = next(draft for draft in product.drafts if draft.predicate == "kg.uses")
    assert relation.verification == "needs_review"
    assert any(isinstance(anchor.selector, Whole) for anchor in relation.anchors)
    assert relation.verification_detail is not None
    assert relation.verification_detail.issues[0].code == "evidence"


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (_raw(predicate="invents"), "unknown_relation"),
        (
            RawExtraction(
                entities=_raw().entities,
                relations=(
                    ExtractedRelation(
                        head="Widget", relation="uses", tail="Acme", evidence="Acme uses Widget."
                    ),
                ),
            ),
            "domain_range",
        ),
        (
            RawExtraction(
                entities=(ExtractedEntity(name="Acme", type="organization"),),
                relations=(
                    ExtractedRelation(
                        head="Acme", relation="owns", tail="missing", evidence="Acme owns missing."
                    ),
                ),
            ),
            "endpoint_ambiguous",
        ),
    ],
)
def test_schema_exclusions_become_counted_proposals(raw: RawExtraction, reason: str) -> None:
    """Unknown vocabulary, reversed direction and ambiguous endpoints never enter the graph."""
    product = assemble_extraction(raw, get_schema(), _source("Acme uses Widget."))
    assert _relations(product) == []
    assert product.proposals[0].reason == reason
    assert product.proposals[0].count == 1


def test_missing_endpoint_unique_type_is_preserved_for_review() -> None:
    """A unique range supplies a type while marking the missing declaration explicitly."""
    raw = _raw().model_copy(update={"entities": (_raw().entities[0],)})
    product = assemble_extraction(raw, get_schema(), _source("Acme uses Widget."))
    relation = next(draft for draft in product.drafts if draft.predicate == "kg.uses")
    assert relation.verification == "needs_review"
    assert relation.verification_detail is not None
    assert [(issue.code, issue.role) for issue in relation.verification_detail.issues] == [
        ("endpoint_undeclared", "tail")
    ]
    assert len(product.entities) == 2


def test_missing_endpoint_containment_reuses_declared_entity() -> None:
    """Normalized containment uses an existing declaration without creating a second entity."""
    raw = _raw(head="Acme Team").model_copy(update={"relations": _raw().relations})
    product = assemble_extraction(raw, get_schema(), _source("Acme Team uses Widget."))
    relation = next(draft for draft in product.drafts if draft.predicate == "kg.uses")
    assert relation.subject.display_name == "acme team"
    assert len(product.entities) == 2


def test_nearest_endpoint_ties_choose_earlier_occurrence() -> None:
    """Distance is measured to the evidence interval with stable tie-breaking."""
    assert nearest_span(
        (TextSpan(start=0, end=2), TextSpan(start=8, end=10)), TextSpan(start=4, end=6)
    ) == TextSpan(start=0, end=2)
    assert nearest_span((), None) is None


def test_entity_mentions_include_every_occurrence_and_relation_uses_nearest() -> None:
    """One entity can have several mention drafts but a relation picks nearby endpoints."""
    text = "Acme knows nothing. Acme uses Widget. Acme leaves."
    product = assemble_extraction(_raw(), get_schema(), _source(text))
    mentions = [
        draft
        for draft in product.drafts
        if draft.predicate == "kg.mentions" and draft.subject.display_name == "acme"
    ]
    relation = next(draft for draft in product.drafts if draft.predicate == "kg.uses")
    assert len(mentions) == 3
    assert relation.verification_detail is not None
    assert relation.verification_detail.head == TextSpan(start=20, end=24)


def test_declared_aliases_verify_spelling_variations() -> None:
    """Schema aliases support grounding independently of benchmark aliases."""
    schema = get_schema()
    types = tuple(
        item.model_copy(update={"aliases": {"Acme": ("Example Team",)}})
        if item.name == "organization"
        else item
        for item in schema.entity_types
    )
    schema = KGSchema.model_validate({**schema.model_dump(), "entity_types": types})
    product = assemble_extraction(
        _raw(evidence="Example Team uses Widget."), schema, _source("Example Team uses Widget.")
    )
    assert _relations(product) == ["verified"]


@pytest.mark.parametrize(
    ("text", "quote", "expected"),
    [
        ("甲\uff21\uff23\uff2d\uff25　使用  工具乙", "acme使用工具", (1, 12)),
        ("The \uff21\uff23\uff2d\uff25  team uses tools.", "acme team", (4, 14)),
        (decode_text("Jo\u0301se uses tools.".encode()), "Jóse", (0, 4)),
        ("Straße uses tools.", "STRASSE", (0, 6)),
    ],
)
def test_normalized_matches_retain_original_offsets(
    text: str, quote: str, expected: tuple[int, int]
) -> None:
    """NFKC, whitespace, case folds and NFC decoding preserve source intervals."""
    span = find_spans(text, quote)[0]
    assert (span.start, span.end) == expected
    assert text[span.start : span.end]


def test_blank_or_absent_quotation_has_no_span() -> None:
    """Empty normalized needles never create zero-length verified evidence."""
    assert find_spans("Example", "") == ()
    assert find_spans("Example", "   ") == ()
    assert find_spans("Example", "missing") == ()


def test_identity_normalization_and_versioning_are_deterministic() -> None:
    """Same normalized name retains identity while the projection version advances."""
    left = entity_asset_ref(
        "data",
        "v1",
        ExtractedEntity(name="  \uff21\uff23\uff2d\uff25   Team ", type="organization"),
    )
    right = entity_asset_ref("data", "v2", ExtractedEntity(name="Acme Team", type="organization"))
    assert left.asset_id == right.asset_id
    assert left.version != right.version
    assert normalize_name("  \uff21\uff23\uff2d\uff25   Team ") == "acme team"


def test_cross_document_merge_unions_anchors_and_locations() -> None:
    """Repeated triples become one deterministic assertion with both source documents."""
    first = assemble_extraction(_raw(), get_schema(), _source("Acme uses Widget.", "one"))
    second = assemble_extraction(_raw(), get_schema(), _source("Acme uses Widget.", "two"))
    merged = merge_drafts((*first.drafts, *second.drafts))
    relation = next(draft for draft in merged if draft.predicate == "kg.uses")
    assert len(relation.anchors) == 6
    assert relation.verification_detail is not None
    assert len(relation.verification_detail.locations) == 2
    reverse = merge_drafts((*second.drafts, *first.drafts))
    other = next(draft for draft in reverse if draft.predicate == "kg.uses")
    assert assertion_identity(relation) == assertion_identity(other)


def test_schema_proposal_samples_are_bounded_without_losing_counts() -> None:
    """Reports retain all excluded claim counts and at most twenty representative samples."""
    raw = _raw(predicate="outside")
    raw = raw.model_copy(update={"relations": raw.relations * 23})
    proposal = assemble_extraction(raw, get_schema(), _source("Acme uses Widget.")).proposals[0]
    assert proposal.count == 23
    assert len(proposal.samples) == 20


def test_entity_mentions_include_exact_and_normalized_occurrences() -> None:
    """An exact occurrence does not suppress differently cased or spaced mentions."""
    text = "Acme Team, ACME  TEAM, acme team."
    spans = entity_spans(text, ("Acme Team",))
    assert [text[span.start : span.end] for span in spans] == [
        "Acme Team",
        "ACME  TEAM",
        "acme team",
    ]
    assert find_spans(text, "Acme Team") == (TextSpan(start=0, end=9),)


@pytest.mark.parametrize(
    ("text", "quote", "interval"),
    [
        ("Jóse", "Jo\u0301se", (0, 4)),
        ("Jo\u0301se", "Jóse", (0, 5)),
        ("x\uff21\u030ay", "Å", (1, 3)),
        ("각", "\u1100\u1161\u11a8", (0, 1)),
    ],
)
def test_combining_sequences_match_without_losing_source_boundaries(
    text: str, quote: str, interval: tuple[int, int]
) -> None:
    """Compatibility normalization composes marks while retaining complete source clusters."""
    span = find_spans(text, quote)[0]
    assert (span.start, span.end) == interval
