# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build graph fixtures from recorded model output through the production action and worker."""

from pathlib import Path

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ExecutionError
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.kg_queries import KGQuery
from datakeel.core.models import JsonDocument
from datakeel.sample_kg import recorded_documents
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.kg_queries import query_kg
from datakeel.worker.runner import run_worker


def seed_kg_case(db: Database, directory: Path) -> CaseFixture:
    """Keep the real recorded absent-endpoint example available to read-tool scenarios."""
    document = next(item for item in recorded_documents() if item.id == "zh04")
    path = directory / "recorded-note.txt"
    path.write_text(document.text, encoding="utf-8")
    dataset = import_paths(db, "Generated graph golden fixture", [path])
    version, files = source_manifest(db, dataset.id)
    plan = prepare_action(
        db,
        "run_kg_extraction",
        JsonDocument(root={"dataset_id": dataset.id, "version_id": version}),
    )
    if plan.requires_approval:
        msg = "Recorded fixture unexpectedly required external approval"
        raise ExecutionError(msg)
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run_worker(db, once=True)
    result = query_kg(
        db,
        KGQuery(
            dataset_id=dataset.id, version_id=version, name="Vivo", verification="needs_review"
        ),
    )
    if len(result.relations) != 1:
        msg = "Recorded fixture did not produce the expected absent-endpoint review candidate"
        raise ExecutionError(msg)
    return CaseFixture(
        dataset_id=dataset.id,
        version_id=version,
        file_id=files[0].id,
        relation_id=result.relations[0].assertion.id,
    )
