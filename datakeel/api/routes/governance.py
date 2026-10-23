# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality evaluations, reports, templates, and audited metadata changes."""

from fastapi import APIRouter

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.models import JsonDocument
from datakeel.governance.models import ComplianceView
from datakeel.quality.models import QualityView, ReportView
from datakeel.storage import governance_service as service
from datakeel.storage.governance_service import MetadataInput, QualityInput
from datakeel.storage.views import (
    MetadataChangeView,
    MetadataSavedView,
    MetadataView,
    TemplateView,
)

router = APIRouter(prefix="/api/datasets/{identifier}", tags=["governance"])


@router.get("/quality", response_model_exclude_none=True)
def quality(
    identifier: str, db: DatabaseDependency, *, quarantined: bool | None = None
) -> QualityView:
    """Read the latest manifest quality evaluation."""
    return service.get_quality(db, identifier, quarantined=quarantined)


@router.put("/quality/config", response_model_exclude_none=True)
def quality_config(identifier: str, config: QualityInput, db: DatabaseDependency) -> QualityView:
    """Replace and validate quality scoring overrides."""
    return service.save_quality(db, identifier, config)


@router.get("/report", response_model_exclude_none=True)
def report(identifier: str, db: DatabaseDependency) -> ReportView:
    """Read the evidence-based dataset report."""
    return service.get_report(db, identifier)


@router.put("/template", response_model_exclude_none=True)
def template(identifier: str, value: JsonDocument, db: DatabaseDependency) -> TemplateView:
    """Bind a JSON Schema standard and calculate compliance."""
    return service.save_template(db, identifier, value)


@router.put("/metadata", response_model_exclude_none=True)
def metadata(identifier: str, body: MetadataInput, db: DatabaseDependency) -> MetadataSavedView:
    """Replace metadata and atomically record each changed field."""
    return service.save_metadata(db, identifier, body)


@router.get("/metadata")
def get_metadata(identifier: str, db: DatabaseDependency) -> MetadataView:
    """Read metadata and its bound standard."""
    return service.get_metadata(db, identifier)


@router.get("/metadata/changes")
def changes(identifier: str, db: DatabaseDependency) -> list[MetadataChangeView]:
    """Read the dataset's ordered metadata audit trail."""
    return service.metadata_changes(db, identifier)


@router.get("/compliance", response_model_exclude_none=True)
def compliance(identifier: str, db: DatabaseDependency) -> ComplianceView:
    """Read naming, directory, and metadata compliance."""
    return service.get_compliance(db, identifier)
