# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local production fixtures shared by transaction and boundary regressions."""

from datakeel.actions.production_parameters import CreateProjectParams, SplitPackagesParams
from datakeel.core.models import FileItem, new_id, utcnow
from datakeel.core.production_catalog_models import LabelSet, ProductionLabel
from datakeel.core.production_models import ProductionTask, Project, WorkflowTier
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.production_projects import create_project, split_packages
from datakeel.storage.production_queries import list_tasks


def production_fixture(
    db: Database,
    tier: WorkflowTier = "personal",
    count: int = 3,
    package_size: int = 100,
) -> tuple[Project, tuple[ProductionTask, ...]]:
    """Create synthetic manifests and a published vocabulary without external files or services."""
    files = [
        FileItem(
            id=new_id(),
            path=f"generated/{index}.png",
            filename=f"{index}.png",
            metadata={"width": 100, "height": 100},
        )
        for index in range(count)
    ]
    labels = _labels()
    with db.session() as session:
        db.lock_writes(session)
        dataset = DatasetRow(
            name="Generated production", files=[item.model_dump(mode="json") for item in files]
        )
        session.add(dataset)
        session.flush()
        version = VersionRow(dataset_id=dataset.id, manifest=dataset.files)
        session.add(version)
        session.add(
            ProductionLabelSetRow(
                id=labels.id + ":1",
                label_set_id=labels.id,
                version=1,
                published=True,
                payload=labels.model_dump(mode="json"),
            )
        )
        session.flush()
        project = create_project(
            session,
            CreateProjectParams(
                request_id=new_id(),
                name="Generated project",
                dataset_id=dataset.id,
                version_id=version.id,
                label_set_id=labels.id,
                workflow_tier=tier,
            ),
            "local",
        )
        split_packages(
            session,
            SplitPackagesParams(
                request_id=new_id(), project_id=project.id, package_size=package_size
            ),
        )
        session.commit()
    return project, list_tasks(db, project.id)


def _labels() -> LabelSet:
    return LabelSet(
        id=new_id(),
        version=1,
        name="Generated labels",
        published=True,
        labels=(ProductionLabel(id="cat", name="Cat"),),
        created_at=utcnow(),
    )
