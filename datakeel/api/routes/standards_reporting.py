# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose field quality and analysis without changing legacy dataset response schemas."""

from fastapi import APIRouter

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.standard_reporting_models import StandardsQuality
from datakeel.quality.models import ReportView
from datakeel.quality.standards import score_standards, standards_report
from datakeel.storage.standard_queries import standards_report as read_report

router = APIRouter(prefix="/api/standards", tags=["standards"])


@router.get("/quality")
def quality(db: DatabaseDependency, table_id: str | None = None) -> StandardsQuality:
    """Score observed completeness, consistency and domain rules for confirmed mappings."""
    return score_standards(read_report(db, table_id))


@router.get("/analysis-report")
def analysis_report(db: DatabaseDependency, table_id: str | None = None) -> ReportView:
    """Build the deterministic analysis report from the same checked column population."""
    return standards_report(read_report(db, table_id))
