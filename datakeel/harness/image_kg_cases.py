# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build image golden fixtures through production replay, preparation and worker execution."""

import shutil
from pathlib import Path

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ExecutionError
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.kg_queries import KGQuery
from datakeel.core.models import JsonDocument
from datakeel.kg.loader import contracts_path
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.kg_queries import query_kg
from datakeel.worker.runner import run_worker


def seed_image_kg_case(db: Database, directory: Path) -> CaseFixture:
    """Keep a text image and a diagram with real recorded relations for tool scenarios."""
    images = contracts_path() / "eval/image/images"
    paths = [
        Path(shutil.copyfile(images / name, directory / name))
        for name in ("en01_clean.png", "b01.png")
    ]
    dataset = import_paths(db, "Generated image graph golden fixture", paths)
    version, files = source_manifest(db, dataset.id)
    plan = prepare_action(
        db,
        "run_kg_extraction",
        JsonDocument(
            root={
                "dataset_id": dataset.id,
                "version_id": version,
                "profile_id": "replay-image-flash",
                "transcription_profile_id": "replay-image-demo",
            }
        ),
    )
    if plan.requires_approval:
        msg = "Offline image fixture unexpectedly required external approval"
        raise ExecutionError(msg)
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run_worker(db, once=True)
    result = query_kg(db, KGQuery(dataset_id=dataset.id, version_id=version))
    relation = next(
        (
            item
            for item in result.relations
            if any(anchor.selector.type == "image_region" for anchor in item.assertion.anchors)
        ),
        None,
    )
    if relation is None:
        msg = "Image fixture did not produce a relation located on its source image"
        raise ExecutionError(msg)
    return CaseFixture(
        dataset_id=dataset.id,
        version_id=version,
        file_id=files[0].id,
        relation_id=relation.assertion.id,
    )
