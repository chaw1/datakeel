# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Directory imports record each file's path under the import root and every image's size."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import FileItem
from datakeel.core.workbench_models import WorkbenchProjectQuery
from datakeel.storage.database import VersionRow
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.workbench_reads import workbench_project
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

# Two levels of folders with the same file names inside, a hidden file and an unreadable image.
LAYOUT = {
    "site-a/day-1/shelf.png": (40, 30),
    "site-a/day-2/shelf.png": (50, 20),
    "site-b/day-1/shelf.png": (64, 48),
    "site-b/day-1/aisle.png": (32, 32),
    "top.png": (16, 12),
}


def build_tree(root: Path) -> Path:
    """Write the generated layout; the caller imports the returned root directory."""
    for relative, size in LAYOUT.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (90, 120, 60)).save(target)
    (root / "site-b" / "broken.png").write_bytes(b"not an image")
    (root / "site-a" / ".DS_Store").write_bytes(b"finder")
    return root


def manifest(db: Database, dataset_id: str) -> list[FileItem]:
    """Read the dataset's first immutable manifest."""
    version = list_versions(db, dataset_id)[0]
    with db.session() as session:
        row = session.get(VersionRow, version.id)
        assert row is not None
        return [FileItem.model_validate(item) for item in row.manifest]


def test_directory_import_records_relative_paths_and_image_sizes(
    db: Database, tmp_path: Path
) -> None:
    """Same-named files stay apart by path; unreadable images record an unknown size."""
    root = build_tree(tmp_path / "import-root")
    dataset = import_paths(db, "Nested shelves", [root])
    files = {item.metadata["relative_path"]: item for item in manifest(db, dataset.id)}
    assert set(files) == {*LAYOUT, "site-b/broken.png"}
    for relative, (width, height) in LAYOUT.items():
        item = files[relative]
        assert item.filename == relative.rsplit("/", 1)[-1]
        assert (item.metadata["width"], item.metadata["height"]) == (width, height)
    broken = files["site-b/broken.png"].metadata
    assert "width" in broken
    assert (broken["width"], broken["height"]) == (None, None)


def test_files_named_directly_keep_only_their_file_name(db: Database, tmp_path: Path) -> None:
    """A plain file import records its size but no directory, exactly as before."""
    root = build_tree(tmp_path / "plain")
    dataset = import_paths(db, "Plain", [root / "top.png"])
    (item,) = manifest(db, dataset.id)
    assert "relative_path" not in item.metadata
    assert (item.filename, item.metadata["width"], item.metadata["height"]) == ("top.png", 16, 12)


def nested_project(db: Database, tmp_path: Path) -> str:
    """Import the nested tree and open a personal project over it."""
    dataset = import_paths(db, "Nested shelves", [build_tree(tmp_path / "import-root")])
    runner = ServiceRunner(db)
    runner("create_label_set", {"label_set_id": "nested", "labels": [{"id": "cat", "name": "Cat"}]})
    runner("publish_label_set", {"label_set_id": "nested", "version": 1})
    project = runner(
        "create_project",
        {
            "name": "Nested",
            "dataset_id": dataset.id,
            "version_id": list_versions(db, dataset.id)[0].id,
            "label_set_id": "nested",
        },
    ).root["id"]
    assert isinstance(project, str)
    runner("split_packages", {"project_id": project, "package_size": 10})
    return project


def test_task_list_shows_relative_paths_and_searches_folders_without_machine_paths(
    db: Database, tmp_path: Path
) -> None:
    """Hover paths tell same-named files apart, a folder name finds its files, no absolute path."""
    project = nested_project(db, tmp_path)
    caller = AccessContext(actor="local", entry="ask", scope="query")
    page = workbench_project(db, project, caller)
    paths = sorted(item.path for item in page.task_samples)
    assert paths == sorted([*LAYOUT, "site-b/broken.png"])
    assert {item.name for item in page.task_samples} == {
        "shelf.png",
        "aisle.png",
        "top.png",
        "broken.png",
    }
    found = workbench_project(db, project, caller, WorkbenchProjectQuery(search="day-1"))
    names = {item.task_id: item.path for item in found.task_samples}
    assert {names[task.id] for task in found.tasks} == {
        "site-a/day-1/shelf.png",
        "site-b/day-1/shelf.png",
        "site-b/day-1/aisle.png",
    }
    assert str(tmp_path) not in page.model_dump_json()


def test_relative_path_mutation_guard(db: Database, tmp_path: Path) -> None:
    """One measured anchor: nested files keep distinct paths in the manifest and the task list."""
    project = nested_project(db, tmp_path)
    caller = AccessContext(actor="local", entry="ask", scope="query")
    page = workbench_project(db, project, caller)
    expected = sorted([*LAYOUT, "site-b/broken.png"])
    assert sorted(item.path for item in page.task_samples) == expected
    dataset = import_paths(db, "Guard", [build_tree(tmp_path / "guard")])
    recorded = sorted(str(item.metadata.get("relative_path")) for item in manifest(db, dataset.id))
    assert recorded == expected
