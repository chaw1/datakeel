# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomic metadata, standard-template, and quality configuration services."""

import json

from pydantic import ConfigDict, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.models import JsonDocument
from datakeel.core.settings import get_settings
from datakeel.governance import compliance_score, validate_metadata
from datakeel.governance.models import ComplianceView
from datakeel.quality import build_report, score_quality
from datakeel.quality.models import QualityView, ReportView
from datakeel.storage.database import Database, DatasetRow, MetadataChangeRow
from datakeel.storage.dataset_service import list_datasets, require_dataset
from datakeel.storage.datasets import dataset_dict, latest_files
from datakeel.storage.dq_views import attach_rule_quality
from datakeel.storage.views import (
    DatasetQualityView,
    MetadataChangeView,
    MetadataSavedView,
    MetadataView,
    TemplateView,
    View,
)


class MetadataInput(View):
    """Replacement metadata with an explicit audit reason."""

    values: dict[str, JsonValue]
    source: str = "api"
    reason: str = Field(min_length=1)


class QualityInput(View):
    """Partial configuration for the five measured quality dimensions."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    weights: dict[str, float] | None = None
    thresholds: dict[str, float] | None = None
    exclude_annotation_when_absent: bool | None = None
    distribution_field: str | None = None
    min_size_bytes: int | None = None
    min_image_width: int | None = None
    min_image_height: int | None = None
    allowed_formats: dict[str, list[str]] | None = None


def get_quality(db: Database, identifier: str, *, quarantined: bool | None = None) -> QualityView:
    """Evaluate quality using the latest published manifest."""
    with db.session() as session:
        row = require_dataset(session, identifier)
        files = latest_files(session, row)
        if quarantined is not None:
            files = [
                item for item in files if bool(item.metadata.get("quarantined")) == quarantined
            ]
        return attach_rule_quality(session, identifier, score_quality(files, row.quality_config))


def dataset_quality_summaries(db: Database) -> list[DatasetQualityView]:
    """Read the same latest-manifest scores as the quality endpoint for each dataset."""
    result: list[DatasetQualityView] = []
    for item in list_datasets(db):
        quality = get_quality(db, item.id)
        result.append(
            DatasetQualityView(
                **item.model_dump(),
                quality_score=quality.total
                if quality.file_count
                or (quality.rules is not None and quality.rules.score is not None)
                else None,
            )
        )
    return result


def save_quality(db: Database, identifier: str, body: QualityInput) -> QualityView:
    """Validate and atomically replace dataset quality overrides."""
    with db.session() as session:
        db.lock_writes(session)
        row = require_dataset(session, identifier, lock=True)
        config = body.model_dump(exclude_unset=True)
        result = attach_rule_quality(
            session, identifier, score_quality(latest_files(session, row), config)
        )
        row.quality_config = config
        session.commit()
        return result


def get_report(db: Database, identifier: str) -> ReportView:
    """Build an evidence-based report from the current dataset snapshot."""
    with db.session() as session:
        row = require_dataset(session, identifier)
        result = attach_rule_quality(
            session, identifier, score_quality(latest_files(session, row), row.quality_config)
        )
        return ReportView.model_validate(
            build_report(dataset_dict(row), result, get_settings().llm_url)
        )


def save_template(db: Database, identifier: str, body: JsonDocument) -> TemplateView:
    """Bind a validated template and persist its current compliance assessment."""
    with db.session() as session:
        db.lock_writes(session)
        row = require_dataset(session, identifier, lock=True)
        result = ComplianceView.model_validate(
            compliance_score(row.name, latest_files(session, row), row.metadata_values, body.root)
        )
        row.template = body.root
        row.compliance = result.model_dump(mode="json", exclude_none=True)
        session.commit()
        return TemplateView(template=body.root, compliance=result)


def _record_changes(session: Session, row: DatasetRow, body: MetadataInput) -> None:
    for field in sorted(row.metadata_values.keys() | body.values.keys()):
        before, after = row.metadata_values.get(field), body.values.get(field)
        if json.dumps(before, sort_keys=True) != json.dumps(after, sort_keys=True) or (
            field in row.metadata_values
        ) != (field in body.values):
            session.add(
                MetadataChangeRow(
                    dataset_id=row.id,
                    field=field,
                    before=before,
                    after=after,
                    source=body.source,
                    reason=body.reason,
                )
            )


def save_metadata(db: Database, identifier: str, body: MetadataInput) -> MetadataSavedView:
    """Validate metadata and commit its field audit in the same transaction."""
    with db.session() as session:
        db.lock_writes(session)
        row = require_dataset(session, identifier, lock=True)
        if row.template:
            validate_metadata(row.template, body.values)
        _record_changes(session, row, body)
        result = ComplianceView.model_validate(
            compliance_score(row.name, latest_files(session, row), body.values, row.template)
        )
        row.metadata_values = body.values
        row.compliance = result.model_dump(mode="json", exclude_none=True)
        session.commit()
        return MetadataSavedView(values=body.values, compliance=result)


def get_metadata(db: Database, identifier: str) -> MetadataView:
    """Read metadata and its bound standard."""
    with db.session() as session:
        row = require_dataset(session, identifier)
        return MetadataView(values=row.metadata_values, template=row.template)


def metadata_changes(db: Database, identifier: str) -> list[MetadataChangeView]:
    """Read ordered field-level metadata audit evidence."""
    with db.session() as session:
        require_dataset(session, identifier)
        return [
            MetadataChangeView(
                field=row.field,
                before=row.before,
                after=row.after,
                source=row.source,
                reason=row.reason,
                occurred_at=row.occurred_at,
            )
            for row in session.scalars(
                select(MetadataChangeRow)
                .where(MetadataChangeRow.dataset_id == identifier)
                .order_by(MetadataChangeRow.occurred_at)
            )
        ]


def get_compliance(db: Database, identifier: str) -> ComplianceView:
    """Calculate naming, directory and metadata compliance from stored evidence."""
    with db.session() as session:
        row = require_dataset(session, identifier)
        return ComplianceView.model_validate(
            compliance_score(
                row.name, latest_files(session, row), row.metadata_values, row.template
            )
        )
