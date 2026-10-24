# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed attributed recorded and scripted graph demonstrations through controlled actions."""

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ExecutionError
from datakeel.core.kg_execution import KGRun
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.sample_kg import generate_kg_samples
from datakeel.storage.database import Database, data_dir
from datakeel.storage.dataset_service import import_paths, list_datasets
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.kg_store import list_runs

KG_DEMO_NAME = "Business notes · knowledge graph demo"


class KGDemoSeed(BoundaryModel):
    """Track the two independently attributed worker tasks for one source graph version."""

    dataset_id: str
    version_id: str
    task_ids: tuple[str, str]


def _schedule(db: Database, params: RunKGExtractionParams) -> str:
    plan = prepare_action(
        db, "run_kg_extraction", JsonDocument.model_validate(params.model_dump(mode="json"))
    )
    if plan.requires_approval:
        msg = "The bundled graph demo must remain fully offline"
        raise ExecutionError(msg)
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.task_id is None:
        msg = f"Graph demo could not schedule its worker task: {run.status}"
        raise ExecutionError(msg)
    return run.task_id


def seed_kg_demo(db: Database) -> KGDemoSeed:
    """Import all source documents and submit separate recorded and scripted extractions."""
    dataset = next((item for item in list_datasets(db) if item.name == KG_DEMO_NAME), None)
    if dataset is None:
        files = generate_kg_samples(data_dir() / "kg-samples")
        dataset = import_paths(
            db,
            KG_DEMO_NAME,
            list(files.paths),
            {
                "kg_samples": True,
                "description": (
                    "24 recorded passages, 3 scripted long documents, 1 scripted truncation."
                ),
                "license": "https://spdx.org/licenses/Apache-2.0.html",
                "creator": "Datakeel sample generator",
            },
        )
    version_id, manifest = source_manifest(db, dataset.id)
    recorded = tuple(item.id for item in manifest if not item.filename.startswith("scripted-long-"))
    scripted = tuple(item.id for item in manifest if item.filename.startswith("scripted-long-"))
    shared = RunKGExtractionParams(dataset_id=dataset.id, version_id=version_id)
    return KGDemoSeed(
        dataset_id=dataset.id,
        version_id=version_id,
        task_ids=(
            _schedule(db, shared.model_copy(update={"file_ids": recorded})),
            _schedule(
                db, shared.model_copy(update={"file_ids": scripted, "profile_id": "fake-long"})
            ),
        ),
    )


def demo_reports(db: Database, seed: KGDemoSeed) -> tuple[KGRun, ...]:
    """Return only this invocation's worker reports, including the deliberate failure block."""
    return tuple(
        run
        for run in list_runs(db, seed.dataset_id, seed.version_id)
        if run.task_id in seed.task_ids
    )


def check_demo(db: Database, seed: KGDemoSeed) -> None:
    """Require both jobs to finish while retaining the deliberately partial recorded run."""
    reports = demo_reports(db, seed)
    if len(reports) != len(seed.task_ids) or any(
        run.status not in {"completed", "partial"} for run in reports
    ):
        msg = "Graph demo extraction did not finish"
        raise ExecutionError(msg)
