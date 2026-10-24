# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Knowledge graph queries, immutable sources and extraction/evaluation history."""

from typing import Annotated

from fastapi import APIRouter, Query

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.harness_models import ModelCallTrace
from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
from datakeel.core.kg_eval_models import KGEvalReport
from datakeel.core.kg_execution import KGRun
from datakeel.core.kg_queries import (
    KGGraph,
    KGQuery,
    KGQueryResult,
    KGRelationExplanation,
    KGSourceText,
)
from datakeel.kg.loader import contracts_path, load_profile, load_schema
from datakeel.storage import kg_queries
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_evaluations import list_evaluations
from datakeel.storage.kg_store import get_job, list_runs

router = APIRouter(prefix="/api/kg", tags=["knowledge graph"])


@router.post("/query")
def query(body: KGQuery, db: DatabaseDependency) -> KGQueryResult:
    """Read filtered entities and candidate or decided relationships."""
    return kg_queries.query_kg(db, body)


@router.get("/relations/{assertion_id}")
def relation(assertion_id: str, db: DatabaseDependency) -> KGRelationExplanation:
    """Explain the exact source checks and model attribution for one relationship."""
    return kg_queries.explain_relation(db, assertion_id)


@router.post("/graph")
def graph(body: KGQuery, db: DatabaseDependency) -> KGGraph:
    """Return a bounded graph with accepted alias display groups."""
    return kg_queries.graph_kg(db, body)


@router.get("/sources/{file_id}")
def source(
    file_id: str,
    db: DatabaseDependency,
    version_id: Annotated[str, Query(min_length=1)],
    extraction_id: Annotated[str | None, Query(min_length=1)] = None,
) -> KGSourceText:
    """Read the frozen normalized text underlying displayed code-point offsets."""
    return kg_queries.get_source_text(db, file_id, version_id, extraction_id)


@router.get("/schemas")
def schemas() -> tuple[KGSchema, ...]:
    """List validated graph vocabularies available to extraction plans."""
    return tuple(load_schema(path) for path in sorted(contracts_path().glob("*.yaml")))


@router.get("/profiles")
def profiles() -> tuple[ExtractionProfile, ...]:
    """List profiles containing only credential environment variable names."""
    return tuple(
        load_profile(path) for path in sorted((contracts_path() / "profiles").glob("*.yaml"))
    )


@router.get("/evaluations")
def evaluations(
    db: DatabaseDependency, limit: Annotated[int, Query(ge=1, le=1000)] = 100
) -> tuple[KGEvalReport, ...]:
    """Read prior graph evaluations in newest-first order."""
    return list_evaluations(db, limit)


@router.get("/runs")
def runs(
    db: DatabaseDependency,
    dataset_id: str | None = None,
    version_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> tuple[KGRun, ...]:
    """Read extraction reports without exposing private frozen request data."""
    return list_runs(db, dataset_id, version_id, limit)


@router.get("/runs/{extraction_id}/traces")
def traces(extraction_id: str, db: DatabaseDependency) -> tuple[ModelCallTrace, ...]:
    """List every metered model attempt belonging to one existing extraction run."""
    get_job(db, extraction_id)
    return tuple(list_traces(db, extraction_id))
