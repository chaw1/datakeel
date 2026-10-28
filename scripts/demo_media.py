# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate and evaluate a local-only image and indoor point-cloud dataset."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from rich.console import Console

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.core.settings import get_settings
from datakeel.lineage.models import GraphQuery
from datakeel.operators.pointcloud.io import dump_cloud
from datakeel.operators.pointcloud.models import CloudField, PointCloud
from datakeel.pipeline.media import media_pipeline
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.governance_service import get_quality, get_report
from datakeel.storage.lineage_service import get_graph
from datakeel.storage.task_queries import query_task
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from numpy.typing import NDArray


class MediaDemoResult(BoundaryModel):
    """Summarize the generated local artifacts and completed pipeline."""

    dataset_id: str
    task_id: str
    state: str
    source_files: int
    pointcloud_files: int
    image_files: int
    versions: int
    lineage_events: int
    quality_score: float
    issue_codes: list[str]
    file_issues: dict[str, list[str]]
    elapsed_seconds: float
    offline: bool = True


def _room_points() -> "NDArray[np.float32]":
    axis_x = np.linspace(-4, 4, 128, dtype=np.float32)
    axis_y = np.linspace(-3, 3, 96, dtype=np.float32)
    axis_z = np.linspace(0, 3, 48, dtype=np.float32)
    x, y = np.meshgrid(axis_x, axis_y)
    wall_y, wall_z = np.meshgrid(axis_y, axis_z)
    return np.concatenate(
        [
            np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)]),
            np.column_stack([wall_y.ravel() * 0 - 4, wall_y.ravel(), wall_z.ravel()]),
            np.column_stack([wall_y.ravel() * 0 + 4, wall_y.ravel(), wall_z.ravel()]),
        ]
    ).astype(np.float32)


def _cloud(points: "NDArray[np.float32]", extension: str) -> PointCloud:
    fields = tuple(CloudField(name=name, dtype="f4") for name in ("x", "y", "z", "intensity"))
    data: NDArray[np.void] = np.zeros(len(points), dtype=[(field.name, "f4") for field in fields])
    for index, name in enumerate(("x", "y", "z")):
        data[name] = points[:, index]
    data["intensity"] = np.linspace(0, 1, len(points), dtype=np.float32)
    return PointCloud(
        format="ply" if extension == "ply" else "pcd",
        encoding="ascii",
        fields=fields,
        data=data,
    )


def _pointclouds(directory: Path) -> list[Path]:
    room = _room_points()
    invalid = room.copy()
    invalid[::4, 0] = np.nan
    invalid[1, 1] = np.inf
    strays = np.random.default_rng(18).uniform(-200, 200, (600, 3))
    floating = np.random.default_rng(20).normal((0, 0, 1.5), 0.05, (40, 3))
    outliers = np.concatenate([strays, floating]).astype(np.float32)
    cases = [
        ("room-normal.ply", room, "binary_little_endian"),
        ("room-millimeters.pcd", room * 1000, "binary"),
        ("room-outliers.ply", np.concatenate([room, outliers]), "ascii"),
        ("room-invalid.pcd", invalid, "ascii"),
        ("room-sparse.ply", room[::96], "binary_big_endian"),
    ]
    paths: list[Path] = []
    for filename, points, encoding in cases:
        path = directory / filename
        cloud = _cloud(points, path.suffix.removeprefix("."))
        path.write_bytes(dump_cloud(cloud.model_copy(update={"encoding": encoding})))
        paths.append(path)
    return paths


def _images(directory: Path) -> list[Path]:
    x, y = np.meshgrid(np.arange(640), np.arange(480))
    tiles = (60 + 130 * ((x // 24 + y // 24) % 2)).astype(np.uint8)
    clear = Image.fromarray(np.stack([tiles, np.roll(tiles, 12, axis=1), tiles], axis=-1))
    draw = ImageDraw.Draw(clear)
    draw.rectangle((120, 100, 400, 340), outline=(220, 190, 100), width=5)
    draw.line((40, 430, 590, 50), fill=(30, 70, 140), width=3)
    pixels = np.asarray(clear).astype(np.float32)
    noise = np.random.default_rng(19).normal(0, 45, pixels.shape)
    cases = {
        "image-clear.png": clear,
        "image-blur-mild.png": clear.filter(ImageFilter.GaussianBlur(2)),
        "image-blur-strong.png": clear.filter(ImageFilter.GaussianBlur(6)),
        "image-overexposed.png": Image.fromarray((250 + pixels / 64).astype(np.uint8)),
        "image-underexposed.png": Image.fromarray((pixels / 64).astype(np.uint8)),
        "image-noisy.png": Image.fromarray(np.clip(pixels + noise, 0, 255).astype(np.uint8)),
        "image-low-resolution.png": clear.resize((64, 48)),
        "image-solid.png": Image.new("RGB", (640, 480), (120, 120, 120)),
    }
    paths: list[Path] = []
    for filename, image in cases.items():
        path = directory / filename
        image.save(path)
        paths.append(path)
    return paths


def generate_media(directory: Path) -> list[Path]:
    """Create deterministic samples with obvious coordinate and image defects."""
    directory.mkdir(parents=True, exist_ok=True)
    return _pointclouds(directory) + _images(directory)


def _save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_demo(output: Path) -> MediaDemoResult:
    """Run the generated samples through a fresh local SQLite worker and report."""
    started = time.perf_counter()
    output = output.resolve()
    settings = get_settings()
    expected_url = f"sqlite:///{output / 'state' / 'datakeel.db'}"
    if settings.home != output / "state" or settings.database_url != expected_url:
        msg = "Run this demo through its CLI to select the isolated local configuration"
        raise ValidationError(msg)
    if settings.llm_url is not None or settings.s3_bucket is not None:
        msg = "Media demo requires local object storage and rule-only reports"
        raise ValidationError(msg)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        msg = "Media demo output must be a new or empty directory"
        raise ValidationError(msg)
    paths = generate_media(output / "samples")
    (output / "state").mkdir()
    db = Database(expected_url)
    try:
        db.migrate()
        dataset = import_paths(db, "Indoor scan and image quality", paths)
        task_id = DatabaseQueue(db).submit(
            dataset.id, "generated-media-v1", media_pipeline(sensor="terrestrial")
        )
        run_worker(db, once=True)
        task = query_task(db, task_id)
        if task.state != "COMPLETED":
            raise ExecutionError(task.error or task.state)
        return _write_results(db, output, dataset.id, task_id, started)
    finally:
        db.engine.dispose()


def _write_results(
    db: Database, output: Path, dataset_id: str, task_id: str, started: float
) -> MediaDemoResult:
    quality = get_quality(db, dataset_id)
    report = get_report(db, dataset_id)
    versions = list_versions(db, dataset_id)
    originals = min(versions, key=lambda version: version.created_at).manifest
    lineage = get_graph(db, query=GraphQuery(asset_id=dataset_id, max_nodes=1000))
    _save_json(output / "quality.json", quality.model_dump(mode="json"))
    _save_json(output / "report.json", report.model_dump(mode="json"))
    _save_json(output / "versions.json", [version.model_dump(mode="json") for version in versions])
    _save_json(output / "lineage.json", lineage.model_dump(mode="json"))
    (output / "report.md").write_text(report.body + "\n", encoding="utf-8")
    result = MediaDemoResult(
        dataset_id=dataset_id,
        task_id=task_id,
        state="COMPLETED",
        source_files=len(originals),
        pointcloud_files=sum(item.modality == "point-cloud" for item in originals),
        image_files=sum(item.modality == "image" for item in originals),
        versions=len(versions),
        lineage_events=len(lineage.events),
        quality_score=quality.total,
        issue_codes=sorted({issue.code for issue in quality.issues if issue.code}),
        file_issues={
            item.filename: sorted(
                {
                    issue.code
                    for issue in quality.issues
                    if issue.code and issue.message.startswith(f"{item.filename}: ")
                }
            )
            for item in originals
        },
        elapsed_seconds=round(time.perf_counter() - started, 3),
    )
    _save_json(output / "summary.json", result.model_dump(mode="json"))
    Console().print(result.model_dump_json(indent=2), markup=False, soft_wrap=True)
    return result


def main() -> None:
    """Use a clean child environment so inherited services and keys are never selected."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New or empty local directory")
    args = parser.parse_args()
    output = args.output.resolve()
    code = """import sys
from pathlib import Path
from scripts.demo_media import run_demo
run_demo(Path(sys.argv[1]))
"""
    subprocess.run(  # noqa: S603  # Fixed interpreter/code, argv path, minimal local-only environment.
        [sys.executable, "-c", code, str(output)],
        cwd=Path(__file__).resolve().parents[1],
        env={
            "DATAKEEL_HOME": str(output / "state"),
            "DATAKEEL_DATABASE_URL": f"sqlite:///{output / 'state' / 'datakeel.db'}",
        },
        check=True,
    )


if __name__ == "__main__":
    main()
