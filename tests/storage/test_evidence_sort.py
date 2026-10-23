# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence ordering is global before limits and remains complete across cursor pages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_models import EvidenceValue
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.storage.evidence_queries import query_evidence
from tests.evidence.interface_fixtures import seed_query_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.evidence.query_models import EvidenceSample
    from datakeel.storage.database import Database


@pytest.fixture
def sorted_dataset(db: Database, tmp_path: Path) -> str:
    """Generate local samples with differing quality, unknowns, names, and candidate counts."""
    return seed_query_evidence(db, tmp_path / "samples")


def _priority(sample: EvidenceSample) -> tuple[int, int, str]:
    unknown = sum(
        isinstance(item.object, EvidenceValue) and item.object.value == "unknown"
        for item in sample.assertions
    )
    candidates = sum(item.status == "candidate" for item in sample.assertions)
    return -unknown, -candidates, sample.asset_ref.asset_id


@pytest.mark.parametrize("sort", ["review", "filename", "quality"])
def test_sorted_query_when_paged_retains_global_order_without_duplicates(
    db: Database,
    sorted_dataset: str,
    sort: Literal["review", "filename", "quality"],
) -> None:
    """Comparing full source facts with every small page catches page-only sorting."""
    original = query_evidence(db, EvidenceQuery(dataset_id=sorted_dataset)).items
    if sort == "review":
        expected = sorted(original, key=_priority)
    elif sort == "filename":
        expected = sorted(
            original, key=lambda sample: (sample.filename.casefold(), sample.asset_ref.asset_id)
        )
    else:
        expected = sorted(
            original, key=lambda sample: (sample.quality_score, sample.asset_ref.asset_id)
        )
    cursor = None
    actual: list[str] = []
    while True:
        query = EvidenceQuery(dataset_id=sorted_dataset, page_size=3, cursor=cursor, sort=sort)
        page = query_evidence(db, query)
        actual.extend(sample.asset_ref.asset_id for sample in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert actual == [sample.asset_ref.asset_id for sample in expected]
    assert len(actual) == len(set(actual)) == 20
    limited = query_evidence(db, EvidenceQuery(dataset_id=sorted_dataset, sort=sort, limit=1))
    assert limited.items[0].asset_ref == expected[0].asset_ref
    assert limited.truncated
    assert limited.total == 1


def test_sorted_query_when_cursor_is_no_longer_selected_requires_restart(
    db: Database,
    sorted_dataset: str,
) -> None:
    """A stale sorted cursor cannot silently restart a page and repeat reviewed samples."""
    with pytest.raises(ValidationError, match="restart pagination"):
        query_evidence(
            db, EvidenceQuery(dataset_id=sorted_dataset, sort="review", cursor="missing")
        )
    assert "sort" not in EvidenceQuery(sort="review").selection().model_dump()
