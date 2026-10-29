# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated project fixtures shared by production catalog regression tests."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import (
    CreateLabelSetParams,
    PublishLabelSetParams,
    RegisterModelParams,
)
from datakeel.actions.production_parameters import CreateProjectParams, SplitPackagesParams
from datakeel.core.models import FileItem
from datakeel.core.production_catalog_models import ProductionLabel, ProductionModel
from datakeel.core.production_models import ProductionTask, Project
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.production_catalog_changes import (
    create_label_set,
    publish_label_set,
    save_model,
)
from datakeel.storage.production_projects import create_project, split_packages
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_tasks import task_view


@dataclass(frozen=True)
class CatalogFixture:
    """Keep generated public boundary objects instead of leaking live ORM rows."""

    project: Project
    tasks: tuple[ProductionTask, ...]


def catalog_project(db: Database) -> CatalogFixture:
    """Create two generated image tasks and an offline model without any external access."""
    with db.session() as session:
        _source(session)
        _catalog(session)
        project = create_project(
            session,
            CreateProjectParams(
                request_id="project",
                name="Generated production",
                dataset_id="catalog-data",
                version_id="catalog-source",
                label_set_id="labels",
                template_id=None,
            ),
            "local",
        )
        session.flush()
        split_packages(session, SplitPackagesParams(request_id="split", project_id=project.id))
        session.flush()
        tasks = tuple(
            task_view(task)
            for task in session.scalars(
                select(ProductionTaskRow)
                .where(ProductionTaskRow.project_id == project.id)
                .order_by(ProductionTaskRow.sample_id)
            )
        )
        session.commit()
    return CatalogFixture(project, tasks)


def _source(session: Session) -> None:
    files = [
        FileItem(
            id=f"sample-{index}",
            path=f"sample-{index}.png",
            filename=f"sample-{index}.png",
            modality="image",
            metadata={"width": 100, "height": 80},
        )
        for index in range(2)
    ]
    session.add(
        DatasetRow(
            id="catalog-data",
            name="Generated production images",
            files=[item.model_dump(mode="json") for item in files],
        )
    )
    session.flush()
    session.add(
        VersionRow(
            id="catalog-source",
            dataset_id="catalog-data",
            manifest=[item.model_dump(mode="json") for item in files],
        )
    )
    session.flush()


def _catalog(session: Session) -> None:
    create_label_set(
        session,
        CreateLabelSetParams(
            request_id="labels",
            label_set_id="labels",
            labels=tuple(
                ProductionLabel(id=value, name=value) for value in ("a", "b", "c", "d", "e")
            ),
        ),
    )
    publish_label_set(
        session, PublishLabelSetParams(request_id="publish", label_set_id="labels", version=1)
    )
    save_model(
        session,
        RegisterModelParams(
            request_id="model",
            model=ProductionModel(
                id="fake",
                name="Generated model",
                version="1",
                provider="fake",
                unit_price=0.25,
            ),
        ),
    )
