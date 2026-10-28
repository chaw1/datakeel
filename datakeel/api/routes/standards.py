# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read standard contracts, rule candidates, confirmed mappings and conformance evidence."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.models import JsonDocument
from datakeel.core.standard_history_models import StandardsHistory, StandardsReport
from datakeel.core.standard_models import (
    CodeList,
    ColumnCheck,
    ColumnMapping,
    ColumnProfile,
    FieldStandard,
    MappingSuggestion,
    StandardsContract,
    StandardsCoverage,
    StandardStatus,
)
from datakeel.standards.loader import contract_schema, dump_contract
from datakeel.storage import standard_queries, standard_store

router = APIRouter(prefix="/api/standards", tags=["standards"])


@router.get("/fields")
def fields(
    db: DatabaseDependency, search: str = "", status: StandardStatus | None = None
) -> tuple[FieldStandard, ...]:
    """Search bilingual field standards and optionally select their lifecycle status."""
    return standard_store.list_standards(db, search, status)


@router.get("/code-lists")
def code_lists(
    db: DatabaseDependency, search: str = "", status: StandardStatus | None = None
) -> tuple[CodeList, ...]:
    """Search reference data names and bilingual value labels by lifecycle status."""
    return standard_store.list_code_lists(db, search, status)


@router.get("/contract")
def contract(db: DatabaseDependency) -> StandardsContract:
    """Read the effective YAML-compatible contract without internal connection metadata."""
    return standard_store.get_contract(db)


@router.get("/export", response_class=PlainTextResponse)
def export(db: DatabaseDependency) -> str:
    """Export the same strict field and code-list definitions as portable YAML."""
    return dump_contract(standard_store.get_contract(db))


@router.get("/schema")
def schema() -> JsonDocument:
    """Return the JSON Schema applied to contract import and controlled edits."""
    return contract_schema()


@router.get("/history")
def history(db: DatabaseDependency) -> StandardsHistory:
    """Read append-only versions with exact action and actor attribution."""
    return standard_store.history(db)


@router.get("/profiles")
def profiles(db: DatabaseDependency) -> tuple[ColumnProfile, ...]:
    """Read column metadata and observed counts without exposing source sample values."""
    return standard_queries.list_profiles(db)


@router.get("/suggestions")
def suggestions(db: DatabaseDependency) -> tuple[MappingSuggestion, ...]:
    """Explain up to three rule candidates per column without confirming them."""
    return standard_queries.suggestions(db)


@router.get("/mappings")
def mappings(db: DatabaseDependency) -> tuple[ColumnMapping, ...]:
    """List only associations explicitly confirmed through controlled actions."""
    return standard_store.list_mappings(db)


@router.get("/report")
def report(db: DatabaseDependency, table_id: str | None = None) -> StandardsReport:
    """Read conformance checks and grouped coverage for all columns or one table."""
    return standard_queries.standards_report(db, table_id)


@router.get("/checks")
def checks(db: DatabaseDependency, table_id: str | None = None) -> tuple[ColumnCheck, ...]:
    """Read redacted rule violations for the currently confirmed mappings."""
    return standard_queries.standards_report(db, table_id).checks


@router.get("/coverage")
def coverage(db: DatabaseDependency) -> StandardsCoverage:
    """Group mapped-column coverage and compliance by source, table and owner."""
    return standard_queries.standards_report(db).coverage
