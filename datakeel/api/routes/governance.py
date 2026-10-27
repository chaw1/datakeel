# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality evaluations, reports, templates, and audited metadata changes."""

from fastapi import APIRouter, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.governance.models import ComplianceView
from datakeel.quality.models import QualityView, ReportView
from datakeel.storage import governance_service as service
from datakeel.storage.data_asset_reads import authorize_query
from datakeel.storage.database import Database
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
    identifier: str, db: DatabaseDependency, request: Request, *, quarantined: bool | None = None
) -> QualityView:
    """Read the latest manifest quality evaluation."""
    result = service.get_quality(db, identifier, quarantined=quarantined)
    _authorize_dataset(db, identifier, request)
    return result


@router.put("/quality/config", response_model_exclude_none=True)
def quality_config(identifier: str, config: QualityInput, db: DatabaseDependency) -> QualityView:
    """Replace and validate quality scoring overrides."""
    return service.save_quality(db, identifier, config)


@router.get("/report", response_model_exclude_none=True)
def report(identifier: str, db: DatabaseDependency, request: Request) -> ReportView:
    """Read the evidence-based dataset report."""
    result = service.get_report(db, identifier)
    _authorize_dataset(db, identifier, request)
    return result


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


def _authorize_dataset(db: Database, identifier: str, request: Request) -> None:
    # Quality findings and reports describe dataset files, so they share the query guard.
    authorize_query(
        db,
        (AssetRef(asset_id=identifier),),
        AccessContext(
            actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="ask", scope="query"
        ),
    )
