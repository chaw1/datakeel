# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish small generated sensor manifests through the real local worker."""

from pathlib import Path

from datakeel.core.profile_models import ProfileDataset
from datakeel.pipeline.tabular import timeseries_pipeline
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.profile_queries import read_profiles
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

SENSOR_QUESTION = "哪台设备的温度数据断档最多"


def publish_sensors(
    db: Database, directory: Path, name: str = "Generated sensors", column: str = "temperature"
) -> ProfileDataset:
    """Store two faulty devices and one gap-free device without any external provider."""
    directory.mkdir(parents=True)
    path = directory / "sensors.csv"
    samples = {"alpha": (5, 0, 1), "beta": (0, 1, 4, 5, 8), "gamma": (0, 1, 2)}
    path.write_text(
        f"timestamp,device_id,{column}\n"
        + "".join(
            f"{1700000000000 + offset * 1000},{device},{20 + offset}\n"
            for device, offsets in samples.items()
            for offset in offsets
        ),
        encoding="utf-8",
    )
    dataset = import_paths(db, name, [path])
    pipeline = timeseries_pipeline(interval_ms=1000)
    DatabaseQueue(db).submit(dataset.id, f"profile:{dataset.id}", pipeline)
    run_worker(db, once=True)
    return next(item.dataset for item in read_profiles(db) if item.dataset.dataset_id == dataset.id)
