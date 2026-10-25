# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed image transcription and graph extraction using only attributed offline replay."""

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.cli.kg_demo import KGDemoSeed
from datakeel.core.errors import ExecutionError
from datakeel.core.models import JsonDocument
from datakeel.sample_image_kg import generate_image_kg_samples
from datakeel.storage.database import Database, data_dir
from datakeel.storage.dataset_service import import_paths, list_datasets
from datakeel.storage.evidence_import import source_manifest

IMAGE_KG_DEMO_NAME = "Images and diagrams · knowledge graph demo"


def _schedule(db: Database, params: RunKGExtractionParams) -> str:
    plan = prepare_action(
        db, "run_kg_extraction", JsonDocument.model_validate(params.model_dump(mode="json"))
    )
    if plan.requires_approval:
        msg = "The bundled image demonstration must remain fully offline"
        raise ExecutionError(msg)
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.task_id is None:
        msg = "Image graph demonstration could not schedule its worker task"
        raise ExecutionError(msg)
    return run.task_id


def seed_image_kg_demo(db: Database) -> KGDemoSeed:
    """Import ten original images and a labelled scripted failure, then schedule both runs."""
    dataset = next((item for item in list_datasets(db) if item.name == IMAGE_KG_DEMO_NAME), None)
    if dataset is None:
        files = generate_image_kg_samples(data_dir() / "image-kg-samples")
        dataset = import_paths(
            db,
            IMAGE_KG_DEMO_NAME,
            list(files.paths),
            {
                "kg_samples": True,
                "image_kg_samples": True,
                "description": (
                    "10 recorded clear, scanned and diagram images, including visual traps. "
                    "One separately labelled scripted transcription truncation."
                ),
                "license": "https://spdx.org/licenses/Apache-2.0.html",
                "creator": "Datakeel sample generator",
            },
        )
    version_id, manifest = source_manifest(db, dataset.id)
    recorded = tuple(item.id for item in manifest if not item.filename.startswith("scripted-"))
    scripted = tuple(item.id for item in manifest if item.filename.startswith("scripted-"))
    shared = RunKGExtractionParams(
        dataset_id=dataset.id, version_id=version_id, profile_id="replay-image-flash"
    )
    return KGDemoSeed(
        dataset_id=dataset.id,
        version_id=version_id,
        task_ids=(
            _schedule(
                db,
                shared.model_copy(
                    update={"file_ids": recorded, "transcription_profile_id": "replay-image-demo"}
                ),
            ),
            _schedule(
                db,
                shared.model_copy(
                    update={
                        "file_ids": scripted,
                        "transcription_profile_id": "replay-image-demo-failure",
                    }
                ),
            ),
        ),
    )
