# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation targets fail with measured assertions when graph safety guards regress."""

import hashlib

from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_models import RawExtraction, TextBlock
from datakeel.core.kg_product import KGSource, ProductExtraction
from datakeel.core.models import AssetRef
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.cache import build_cache_key
from datakeel.kg.loader import get_profile, get_schema


def _product(head: str, tail: str, evidence: str) -> ProductExtraction:
    text = "Cedar Unit uses AtlasBoard."
    return assemble_extraction(
        RawExtraction(
            entities=(
                ExtractedEntity(name=head, type="organization"),
                ExtractedEntity(name=tail, type="system"),
            ),
            relations=(
                ExtractedRelation(head=head, relation="uses", tail=tail, evidence=evidence),
            ),
        ),
        get_schema(),
        KGSource(
            dataset_id="fixture",
            dataset_version_id="version",
            file=AssetRef(asset_type="file", asset_id="source", version="version"),
            text=text,
            content_revision=hashlib.sha256(text.encode()).hexdigest(),
            extractor=ExtractorRef(id="fake", version="1"),
        ),
    )


def test_missing_endpoints_cannot_be_verified() -> None:
    """An exact evidence quote cannot verify two invented endpoint names."""
    product = _product("Invented Unit", "Invented Board", "Cedar Unit uses AtlasBoard.")
    relations = [draft for draft in product.drafts if draft.predicate == "kg.uses"]
    assert len(relations) == 1
    assert relations[0].verification == "needs_review"
    detail = relations[0].verification_detail
    assert detail is not None
    assert {issue.code for issue in detail.issues} == {"head", "tail"}


def test_unverified_relations_are_not_discarded() -> None:
    """Retain a paraphrased evidence claim for the human decision path."""
    product = _product("Cedar Unit", "AtlasBoard", "Cedar Unit adopted the platform")
    relations = [draft for draft in product.drafts if draft.predicate == "kg.uses"]
    assert len(relations) == 1
    assert relations[0].verification == "needs_review"


def test_model_name_participates_in_cache_identity() -> None:
    """Changing only the provider model invalidates a content-identical cache entry."""
    text = "Cedar Unit uses AtlasBoard."
    block = TextBlock(text=text, start=0, end=len(text))
    profile, schema = get_profile("fake"), get_schema()
    extractor = ExtractorRef(id="fake", version="1")
    first = build_cache_key(block, schema, profile, extractor).digest()
    second = build_cache_key(
        block, schema, profile.model_copy(update={"model": "different-model"}), extractor
    ).digest()
    assert first != second
