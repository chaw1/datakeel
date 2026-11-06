# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One display order for packages and tasks: the task list, read functions and the planner.

Identities are random, so ordering by id shuffles what people see. Packages are listed in
the order they were made (creation time, then the number in their name); tasks follow their
package and, inside it, the order of the files in the project's dataset version. "The first
three tasks", "#5" and "the second package" all count in this order.
"""

import re
from collections.abc import Callable, Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.production_models import Project, TaskPackage
from datakeel.dataset_store.rows import VersionRow
from datakeel.storage.production_rows import (
    ProductionPackageRow,
    ProductionProjectRow,
    ProductionTaskRow,
)

_NUMBER = re.compile(r"(\d+)")
type NaturalKey = tuple[int | str, ...]
type PackageKey = tuple[datetime, NaturalKey, str]
type TaskKey = tuple[int, int, str]


def _natural(name: str) -> NaturalKey:
    """Numbers in a name compare as numbers: Package 2 comes before Package 10."""
    return tuple(int(part) if part.isdigit() else part.casefold() for part in _NUMBER.split(name))


def package_key(package: TaskPackage) -> PackageKey:
    """Where a package appears in the list."""
    return package.created_at, _natural(package.name), package.id


def ordered_packages(packages: Iterable[TaskPackage]) -> list[TaskPackage]:
    """Packages as the list shows them."""
    return sorted(packages, key=package_key)


def task_key(session: Session, project_id: str) -> Callable[[ProductionTaskRow], TaskKey]:
    """Sort key for one project's task rows: package position, then file position."""
    packages = ordered_packages(
        TaskPackage.model_validate(row.payload)
        for row in session.scalars(
            select(ProductionPackageRow).where(ProductionPackageRow.project_id == project_id)
        )
    )
    rank = {package.id: index for index, package in enumerate(packages)}
    positions: dict[str, int] = {}
    row = session.get(ProductionProjectRow, project_id)
    if row is not None:
        project = Project.model_validate(row.payload)
        version = session.get(VersionRow, project.version_id)
        manifest = version.manifest if version is not None else []
        for index, item in enumerate(manifest):
            identity = item.get("id")
            if isinstance(identity, str):
                positions.setdefault(identity, index)

    def key(task: ProductionTaskRow) -> TaskKey:
        return (
            rank.get(task.package_id, len(rank)),
            positions.get(task.sample_id, len(positions)),
            task.id,
        )

    return key


def ordered_task_rows(
    session: Session, project_id: str, rows: Iterable[ProductionTaskRow]
) -> list[ProductionTaskRow]:
    """Task rows of one project as the task list shows them."""
    return sorted(rows, key=task_key(session, project_id))
