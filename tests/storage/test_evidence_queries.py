# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence filtering and presentation share source facts with frozen controlled selections."""

from pathlib import Path

import pytest
from sqlalchemy import delete

from datakeel.core.errors import NotFoundError
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.ontology.models import AssertionFilter
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_queries import explain_sample, get_evidence, query_evidence
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.object_projection import file_quality
from datakeel.storage.object_queries import evaluate
from tests.evidence.interface_fixtures import seed_query_evidence


@pytest.fixture
def evidence_dataset(db: Database, tmp_path: Path) -> str:
    """Provide complete worker-produced evidence without reading evaluation gold."""
    return seed_query_evidence(db, tmp_path / "samples")


def _sample_id(db: Database, dataset_id: str, path: str) -> str:
    return next(file.id for file in source_manifest(db, dataset_id)[1] if file.filename == path)


def test_query_when_combined_filters_selects_gap_and_preserves_evidence(
    db: Database, evidence_dataset: str
) -> None:
    """Verify the example query uses canonical concepts and exact source versions."""
    query = EvidenceQuery(
        dataset_id=evidence_dataset,
        split="val",
        has_near_duplicate_in="train",
        assertion_filters=[
            AssertionFilter(predicate="mentions", concept="person", value="present"),
            AssertionFilter(
                predicate="annotated_as", concept="person", value="present", operator="not_exists"
            ),
        ],
    )
    result = query_evidence(db, query)
    assert result.total == 1
    sample = result.items[0]
    assert sample.filename == "val/scene-0016/image.png"
    assert sample.source_version == source_manifest(db, evidence_dataset)[0]
    assert sample.thumbnail_url
    assert sample.caption
    assert sample.caption_spans
    assert sample.annotation_boxes
    assert sample.assertions
    assert sample.near_duplicates
    assert all(assertion.anchors and assertion.extractor.version for assertion in sample.assertions)
    frozen = evaluate(db, query.selection())
    assert [value.asset_ref for value in frozen.objects] == [sample.asset_ref]
    assert frozen.objects[0].properties["quality"] == sample.quality_score


def test_query_when_rejected_excluded_detail_still_exposes_inverse_decision(
    db: Database, evidence_dataset: str
) -> None:
    """Verify explicit rejected filters are possible while the default result hides them."""
    identifier = _sample_id(db, evidence_dataset, "val/scene-0016/image.png")
    gap = next(
        item for item in get_evidence(db, identifier).assertions if item.predicate == "label_gap"
    )
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(gap.id,), status="rejected", actor="reviewer", idempotency_key="reject"
        ),
    )
    rule = AssertionFilter(predicate="label_gap", concept="person", value="present")
    assert (
        query_evidence(
            db, EvidenceQuery(dataset_id=evidence_dataset, assertion_filters=[rule])
        ).total
        == 0
    )
    listed = query_evidence(db, EvidenceQuery(dataset_id=evidence_dataset))
    assert all(item.status != "rejected" for sample in listed.items for item in sample.assertions)
    assert any(
        item.id == gap.id and item.status == "rejected"
        for item in get_evidence(db, identifier).assertions
    )
    explicit = query_evidence(
        db,
        EvidenceQuery(
            dataset_id=evidence_dataset,
            assertion_filters=[rule.model_copy(update={"status": ["rejected"]})],
        ),
    )
    assert explicit.total == 1


def test_query_when_unknown_annotation_does_not_claim_absence(
    db: Database, evidence_dataset: str
) -> None:
    """Verify not_exists refers to matching assertions and retains unknown facts."""
    query = EvidenceQuery(
        dataset_id=evidence_dataset,
        split="val",
        assertion_filters=[
            AssertionFilter(predicate="mentions", concept="person", value="present"),
            AssertionFilter(
                predicate="annotated_as", concept="person", value="present", operator="not_exists"
            ),
        ],
    )
    result = query_evidence(db, query)
    assert {item.filename for item in result.items} == {
        "val/scene-0016/image.png",
        "val/scene-0018/image.png",
    }
    identifier = _sample_id(db, evidence_dataset, "val/scene-0018/image.png")
    explanation = explain_sample(db, identifier)
    assert "unknown" in explanation.text
    assert "未知" in explanation.text
    assert any(
        state.predicate == "label_gap" and state.value == "unknown" for state in explanation.states
    )
    assert not any(
        state.predicate == "label_gap" and state.value == "absent" for state in explanation.states
    )


def test_query_when_paginated_has_stable_cursors_and_no_duplicate_ids(
    db: Database, evidence_dataset: str
) -> None:
    """Verify ascending asset identities form stable complete pages."""
    cursor = None
    identifiers = []
    while True:
        query = EvidenceQuery(dataset_id=evidence_dataset, cursor=cursor, page_size=3)
        page = query_evidence(db, query)
        assert page == query_evidence(db, query)
        assert page.total == 20
        identifiers.extend(sample.asset_ref.asset_id for sample in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(identifiers) == len(set(identifiers)) == 20
    assert identifiers == sorted(identifiers)


def test_query_when_legacy_files_mix_filters_pairing_before_limit(
    db: Database, evidence_dataset: str, tmp_path: Path
) -> None:
    """Verify unrelated legacy files cannot consume the evidence result limit."""
    paths = [tmp_path / f"legacy-{index}.txt" for index in range(30)]
    for path in paths:
        path.write_text("generated legacy content", encoding="utf-8")
    import_paths(db, "legacy", paths)
    result = query_evidence(db, EvidenceQuery(limit=20))
    assert result.total == 20
    assert not result.truncated
    assert {sample.dataset_id for sample in result.items} == {evidence_dataset}


def test_query_when_direct_pair_exists_expands_both_ends(
    db: Database, evidence_dataset: str
) -> None:
    """Verify one canonical stored pair is visible from either sample and split filter."""
    train = _sample_id(db, evidence_dataset, "train/scene-0000/image.png")
    val = _sample_id(db, evidence_dataset, "val/scene-0016/image.png")
    assert train in {item.asset_ref.asset_id for item in get_evidence(db, val).near_duplicates}
    assert val in {item.asset_ref.asset_id for item in get_evidence(db, train).near_duplicates}
    result = query_evidence(
        db, EvidenceQuery(dataset_id=evidence_dataset, split="train", has_near_duplicate_in="val")
    )
    assert [sample.asset_ref.asset_id for sample in result.items] == [train]


def test_query_when_corrupt_uses_existing_p1_quality_and_no_thumbnail(
    db: Database, evidence_dataset: str
) -> None:
    """Verify measured decode failure is mapped into the established quality calculation."""
    identifier = _sample_id(db, evidence_dataset, "val/scene-0019/image.png")
    sample = get_evidence(db, identifier)
    assert sample.quality_score == 0
    assert sample.thumbnail_url is None
    result = query_evidence(db, EvidenceQuery(dataset_id=evidence_dataset, quality_max=0))
    assert [item.asset_ref.asset_id for item in result.items] == [identifier]
    _, files = source_manifest(db, evidence_dataset)
    with db.session() as session:
        dataset = session.get(DatasetRow, evidence_dataset)
        assert dataset is not None
        source = next(file for file in files if file.id == identifier)
        measured = source.model_copy(update={"metadata": {**source.metadata, "corrupt": True}})
        assert sample.quality_score == file_quality(measured, dataset)


def test_explain_when_assertions_missing_reports_diagnostic_without_inventing_unknown(
    db: Database, evidence_dataset: str
) -> None:
    """Verify absent projection data cannot conceal a failed unknown-state extraction."""
    identifier = _sample_id(db, evidence_dataset, "val/scene-0018/image.png")
    with db.session() as session:
        session.execute(delete(AssertionRow).where(AssertionRow.subject_id == identifier))
        session.commit()
    result = explain_sample(db, identifier)
    assert "尚无抽取断言" in result.text
    assert result.states == []
    assert result.assertions == []
    assert "unknown" not in result.text


def test_query_when_confidence_bound_applied_filters_unmeasured_claims(
    db: Database, evidence_dataset: str
) -> None:
    """Verify missing confidence cannot satisfy an explicit numeric threshold."""
    query = EvidenceQuery(
        dataset_id=evidence_dataset,
        assertion_filters=[
            AssertionFilter(predicate="mentions", concept="rain", value="unknown", min_confidence=0)
        ],
    )
    assert query_evidence(db, query).total == 0


def test_query_when_missing_identity_raises_not_found(db: Database) -> None:
    """Verify asset lookup errors preserve the standard API error boundary."""
    with pytest.raises(NotFoundError, match="sample"):
        get_evidence(db, "missing")


def test_query_when_multiple_versions_match_deduplicates_latest_before_limit(
    db: Database, evidence_dataset: str
) -> None:
    """Verify unique asset limits, chronological version choice, and exact-version facts."""
    source_id, _ = source_manifest(db, evidence_dataset)
    with db.session() as session:
        source = session.get(VersionRow, source_id)
        assert source is not None
        latest = VersionRow(
            id="zz-latest-selected-version",
            dataset_id=evidence_dataset,
            manifest=source.manifest,
            created_at=source.created_at + 100,
        )
        session.add(latest)
        session.commit()
    query = EvidenceQuery(
        dataset_id=evidence_dataset, version_ids=[source_id, "zz-latest-selected-version"], limit=20
    )
    result = query_evidence(db, query)
    assert result.total == 20
    assert not result.truncated
    assert {item.source_version for item in result.items} == {"zz-latest-selected-version"}
    assert all(item.assertions == [] for item in result.items)
    assert all(item.caption is None for item in result.items)
    item = result.items[0]
    assert item.thumbnail_url
    assert "version=zz-latest-selected-version" in item.thumbnail_url
    assert get_evidence(db, item.asset_ref.asset_id, item.source_version) == item
    assert get_evidence(db, item.asset_ref.asset_id).source_version == source_id
    assert explain_sample(db, item.asset_ref.asset_id, item.source_version).assertions == []
    limited = query_evidence(db, query.model_copy(update={"limit": 3}))
    assert limited.total == 3
    assert limited.truncated


def test_get_evidence_when_source_version_has_no_matching_file_rejects(
    db: Database, evidence_dataset: str
) -> None:
    """Verify a request cannot silently fall back from the specified version."""
    identifier = _sample_id(db, evidence_dataset, "val/scene-0016/image.png")
    with pytest.raises(NotFoundError, match="sample"):
        get_evidence(db, identifier, "different-version")
