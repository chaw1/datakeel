# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Knowledge graph queries, immutable sources and extraction/evaluation history."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.evidence_models import AssertionStatus
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
    KGTranscriptionSelection,
)
from datakeel.core.link_models import EntityLink, LinkRunResult
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.kg.loader import contracts_path, load_profile, load_schema
from datakeel.storage import kg_queries
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_evaluations import list_evaluations
from datakeel.storage.kg_image_sources import image_bytes
from datakeel.storage.kg_run_reads import list_readable_runs
from datakeel.storage.kg_store import get_job
from datakeel.storage.kg_transcription_selection import transcription_selection
from datakeel.storage.link_queries import entity_links, list_links
from datakeel.storage.link_store import relink
from datakeel.transcription.loader import load_profile as load_transcription_profile

router = APIRouter(prefix="/api/kg", tags=["knowledge graph"])


@router.get("/links")
def links(
    db: DatabaseDependency,
    dataset_id: str | None = None,
    status: AssertionStatus | None = None,
) -> tuple[EntityLink, ...]:
    """Read reviewable associations from the latest graph of each selected dataset."""
    return list_links(db, dataset_id, status)


@router.get("/entities/{entity_id}/links")
def associations(entity_id: str, db: DatabaseDependency) -> tuple[EntityLink, ...]:
    """Show exact catalog matches and human decisions for one graph entity."""
    return entity_links(db, entity_id)


@router.post("/links/rerun")
def rerun_links(db: DatabaseDependency) -> LinkRunResult:
    """Refresh deterministic catalog associations without calling a model."""
    return relink(db)


@router.post("/query")
def query(body: KGQuery, db: DatabaseDependency, request: Request) -> KGQueryResult:
    """Read filtered entities and candidate or decided relationships."""
    return kg_queries.query_kg(db, body, access=_query_access(request))


@router.get("/relations/{assertion_id}")
def relation(assertion_id: str, db: DatabaseDependency, request: Request) -> KGRelationExplanation:
    """Explain the exact source checks and model attribution for one relationship."""
    return kg_queries.explain_relation(db, assertion_id, access=_query_access(request))


@router.post("/graph")
def graph(body: KGQuery, db: DatabaseDependency, request: Request) -> KGGraph:
    """Return a bounded graph with accepted alias display groups."""
    return kg_queries.graph_kg(db, body, access=_query_access(request))


@router.get("/sources/{file_id}")
def source(
    file_id: str,
    db: DatabaseDependency,
    request: Request,
    version_id: Annotated[str, Query(min_length=1)],
    extraction_id: Annotated[str | None, Query(min_length=1)] = None,
) -> KGSourceText:
    """Read the frozen normalized text underlying displayed code-point offsets."""
    return kg_queries.get_source_text(
        db, file_id, version_id, extraction_id, access=_query_access(request)
    )


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
    request: Request,
    dataset_id: str | None = None,
    version_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> tuple[KGRun, ...]:
    """Read extraction reports without exposing private frozen request data."""
    # Proposal samples quote source text, so only currently readable sources are listed.
    return list_readable_runs(db, dataset_id, version_id, limit, access=_query_access(request))


@router.get("/runs/{extraction_id}/traces")
def traces(extraction_id: str, db: DatabaseDependency) -> tuple[ModelCallTrace, ...]:
    """List every metered model attempt belonging to one existing extraction run."""
    get_job(db, extraction_id)
    return tuple(list_traces(db, extraction_id))


@router.get("/transcription-profiles")
def list_transcription_profiles() -> tuple[TranscriptionProfile, ...]:
    """List validated image transcription configurations without reading credentials."""
    return tuple(
        profile
        for path in sorted((contracts_path() / "transcription-profiles").glob("*.yaml"))
        if (profile := load_transcription_profile(path)).backend != "fake"
        and not profile.id.endswith("-failure")
    )


@router.get("/transcription-selection")
def select_transcription(
    db: DatabaseDependency,
    dataset_id: Annotated[str, Query(min_length=1)],
    version_id: Annotated[str, Query(min_length=1)],
) -> KGTranscriptionSelection:
    """Show whether the complete version can safely default to the packaged image replay."""
    return transcription_selection(db, dataset_id, version_id)


@router.get(
    "/images/{file_id}",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"description": "Image or extraction run not found"},
        422: {
            "description": "Invalid image request or image revision",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}
            },
        },
    },
)
def image_content(
    file_id: str, version_id: str, extraction_id: str, db: DatabaseDependency, request: Request
) -> Response:
    """Serve orientation-corrected original pixels in the same coordinate system as evidence."""
    access = AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local-user"),
        entry="download",
        scope="download",
    )
    return Response(
        image_bytes(db, file_id, version_id, extraction_id, access=access), media_type="image/png"
    )


def _query_access(request: Request) -> AccessContext:
    return AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="ask", scope="query"
    )
