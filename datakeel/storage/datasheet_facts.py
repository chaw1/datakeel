# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Extract deterministic documentation facts from an explicitly pinned manifest."""

from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.datasheet_models import DatasheetChapter, DatasheetFact
from datakeel.core.errors import NotFoundError
from datakeel.core.models import FileItem, utcnow
from datakeel.governance import compliance_score
from datakeel.quality import score_quality
from datakeel.storage.database import DatasetRow, MetadataChangeRow, VersionRow
from datakeel.storage.dataset_service import require_dataset
from datakeel.storage.datasheet_sources import source_facts
from datakeel.storage.datasheet_values import make_fact

_METADATA_CHAPTERS: dict[DatasheetChapter, tuple[str, ...]] = {
    "motivation": ("description", "purpose", "motivation"),
    "collection": (
        "source",
        "collection_method",
        "collection_period",
        "collection_date",
        "consent",
    ),
    "uses": (
        "intended_use",
        "intended_uses",
        "use_cases",
        "limitations",
        "prohibited_uses",
        "not_recommended",
    ),
    "distribution": ("license", "citation", "access", "distribution", "distribution_policy"),
    "maintenance": ("creator", "owner", "maintainer", "contact", "update_frequency", "retention"),
}


def require_version(session: Session, dataset_id: str, version_id: str) -> VersionRow:
    """Require a real immutable version owned by the requested dataset."""
    row = session.get(VersionRow, version_id)
    if row is None or row.dataset_id != dataset_id:
        msg = "Dataset version not found"
        raise NotFoundError(msg)
    return row


def _manifest_facts(dataset: DatasetRow, version: VersionRow) -> tuple[DatasheetFact, ...]:
    files = [FileItem.model_validate(value) for value in version.manifest]
    created_at = datetime.fromtimestamp(version.created_at, UTC)
    values: tuple[tuple[str, object], ...] = (
        ("manifest.file_count", len(files)),
        ("manifest.modalities", dict(sorted(Counter(item.modality for item in files).items()))),
        ("manifest.total_bytes", sum(item.size for item in files)),
    )
    candidates = [
        make_fact("composition", "version_manifest", version.id, field, value, created_at)
        for field, value in values
    ]
    candidates.extend(
        (
            make_fact(
                "composition",
                "dataset",
                dataset.id,
                "dataset.name",
                dataset.name,
                datetime.fromtimestamp(dataset.created_at, UTC),
            ),
            make_fact(
                "collection",
                "version",
                version.id,
                "version.created_at",
                created_at.isoformat(),
                created_at,
            ),
        )
    )
    filenames = sorted(item.filename for item in files)
    candidates.extend(
        make_fact(
            "composition",
            "version_manifest",
            version.id,
            f"manifest.filenames.{offset // 100 + 1}",
            filenames[offset : offset + 100],
            created_at,
        )
        for offset in range(0, len(filenames), 100)
    )
    return tuple(fact for fact in candidates if fact is not None)


def _metadata_facts(session: Session, dataset: DatasetRow) -> tuple[DatasheetFact, ...]:
    changes = {
        row.field: row.occurred_at
        for row in session.scalars(
            select(MetadataChangeRow)
            .where(MetadataChangeRow.dataset_id == dataset.id)
            .order_by(MetadataChangeRow.occurred_at, MetadataChangeRow.id)
        )
    }
    facts: list[DatasheetFact] = []
    for chapter, fields in _METADATA_CHAPTERS.items():
        for field in fields:
            value = dataset.metadata_values.get(field)
            if value in (None, "", [], {}):
                continue
            fact = make_fact(
                chapter,
                "dataset_metadata",
                dataset.id,
                f"metadata.{field}",
                value,
                datetime.fromtimestamp(changes.get(field, dataset.created_at), UTC),
            )
            if fact is not None:
                facts.append(fact)
    return tuple(facts)


def _assessment_facts(dataset: DatasetRow, version: VersionRow) -> tuple[DatasheetFact, ...]:
    files = [FileItem.model_validate(value) for value in version.manifest]
    measured_at = utcnow()
    quality = score_quality(files, dataset.quality_config)
    compliance = compliance_score(dataset.name, files, dataset.metadata_values, dataset.template)
    values: tuple[tuple[DatasheetChapter, str, str, object], ...] = (
        ("composition", "version_quality", "quality.total", quality.total),
        ("composition", "version_quality", "quality.grade", quality.grade),
        (
            "preprocessing",
            "version_quality",
            "quality.dimensions",
            {key: value.model_dump(mode="json") for key, value in quality.dimensions.items()},
        ),
        (
            "preprocessing",
            "version_quality",
            "quality.issues",
            [item.model_dump(mode="json") for item in quality.issues],
        ),
        ("maintenance", "version_compliance", "compliance.total", compliance.total),
        (
            "maintenance",
            "version_compliance",
            "compliance.issues",
            [item.model_dump(mode="json") for item in compliance.issues],
        ),
    )
    return tuple(
        fact
        for chapter, source, field, value in values
        if (fact := make_fact(chapter, source, version.id, field, value, measured_at)) is not None
    )


def extract_facts(session: Session, dataset_id: str, version_id: str) -> tuple[DatasheetFact, ...]:
    """Freeze manifest, current governance, scoped evidence and lineage with exact attribution.

    Immutable manifest values always come from the requested version, without the
    mutable file-state overlay. Dataset metadata is explicitly attributed to its
    field audit time; newly computed assessments retain their measurement time.
    """
    dataset = require_dataset(session, dataset_id)
    version = require_version(session, dataset_id, version_id)
    facts = (
        *_manifest_facts(dataset, version),
        *_metadata_facts(session, dataset),
        *_assessment_facts(dataset, version),
        *source_facts(session, dataset_id, version),
    )
    return tuple(
        sorted(facts, key=lambda fact: (fact.chapter, fact.source_type, fact.source_id, fact.field))
    )
