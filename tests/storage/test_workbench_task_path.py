# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""An opened task names its file by the path under the import root, like the task list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.data_asset_models import AccessContext
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.workbench_reads import workbench_project, workbench_task
from tests.production_team_support import ServiceRunner
from tests.storage.test_import_layout import LAYOUT, build_tree, nested_project

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

_CALLER = AccessContext(actor="local", entry="ask", scope="query")


def test_opened_task_shows_the_relative_path_listed_for_it(db: Database, tmp_path: Path) -> None:
    """Same-named files in different folders open under their own paths, never a machine path."""
    project = nested_project(db, tmp_path)
    page = workbench_project(db, project, _CALLER)
    listed = {item.task_id: (item.name, item.path) for item in page.task_samples}
    opened: dict[str, tuple[str, str]] = {}
    for task in page.tasks:
        sample = workbench_task(db, task.id, _CALLER).sample
        opened[task.id] = (sample.name, sample.path)
        assert str(tmp_path) not in sample.model_dump_json()
    assert opened == listed
    assert sorted(path for _, path in opened.values()) == sorted([*LAYOUT, "site-b/broken.png"])


def test_opened_task_without_a_recorded_path_shows_the_file_name(
    db: Database, tmp_path: Path
) -> None:
    """A file imported on its own, like data imported before paths were recorded, shows its name."""
    dataset = import_paths(db, "Plain", [build_tree(tmp_path / "plain") / "top.png"])
    runner = ServiceRunner(db)
    runner("create_label_set", {"label_set_id": "plain", "labels": [{"id": "cat", "name": "Cat"}]})
    runner("publish_label_set", {"label_set_id": "plain", "version": 1})
    project = runner(
        "create_project",
        {
            "name": "Plain",
            "dataset_id": dataset.id,
            "version_id": list_versions(db, dataset.id)[0].id,
            "label_set_id": "plain",
        },
    ).root["id"]
    assert isinstance(project, str)
    runner("split_packages", {"project_id": project, "package_size": 10})
    (task,) = workbench_project(db, project, _CALLER).tasks
    sample = workbench_task(db, task.id, _CALLER).sample
    assert (sample.name, sample.path) == ("top.png", "top.png")
