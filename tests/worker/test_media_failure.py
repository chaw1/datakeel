# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Published media lineage must resolve to durable manifests, even after failures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.cli.media_demo import run_demo
from datakeel.core.errors import ExecutionError, NotFoundError
from datakeel.operators import REGISTRY
from datakeel.operators.media.tools import run_tool
from datakeel.pipeline import Node, Pipeline
from datakeel.storage.dataset_service import import_paths, list_versions, task_artifacts
from datakeel.storage.lineage_service import get_graph
from datakeel.storage.task_queries import query_task
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.models import FileItem
    from datakeel.operators.base import OperatorResult, Params
    from datakeel.storage.database import Database


def test_downstream_failure_does_not_publish_unavailable_clip_files(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retain failure audit while withholding file outputs without a published manifest."""
    path = tmp_path / "generated.mkv"
    run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=64x48:r=30:d=0.4",
            "-c:v",
            "ffv1",
            str(path),
        ]
    )
    dataset = import_paths(db, "Generated downstream failure", [path])
    definition = Pipeline(
        nodes=[
            Node(id="route", kind="route", inputs={"files": "$input.files"}),
            Node(
                id="segment",
                operator="video.segment",
                inputs={"files": "route.video"},
                params={"window_ms": 200},
            ),
            Node(id="normalize", operator="video.normalize", inputs={"files": "segment.files"}),
        ],
        outputs=["normalize.files"],
    )

    def fail_normalize(
        _files: list[FileItem], _output_dir: Path, _params: Params
    ) -> OperatorResult:
        msg = "Generated downstream failure after creating temporary clips"
        raise ExecutionError(msg)

    monkeypatch.setattr(REGISTRY["video.normalize"], "execute", fail_normalize)
    task_id = DatabaseQueue(db).submit(dataset.id, "generated-downstream-failure", definition)
    run_worker(db, once=True)
    assert query_task(db, task_id).state == "FAILED"
    assert len(list_versions(db, dataset.id)) == 1
    with pytest.raises(NotFoundError, match="Completed artifacts not found"):
        task_artifacts(db, task_id)
    graph = get_graph(db, dataset.id)
    assert not any(node.asset_type == "file" for node in graph.nodes)
    assert any(
        event.operator == "video.segment" and event.run_state == "COMPLETED"
        for event in graph.events
    )
    assert any(
        event.operator == "video.normalize" and event.run_state == "FAILED"
        for event in graph.events
    )


def test_completed_media_lineage_contains_only_durable_file_objects(db: Database) -> None:
    """Every clickable file has a manifest; final clip lineage retains its full processing."""
    result = run_demo(db)
    dataset_id = str(result["dataset_id"])
    versions = list_versions(db, dataset_id)
    available = {file.id for version in versions for file in version.manifest}
    graph = get_graph(db, dataset_id)
    file_nodes = {node.asset_id for node in graph.nodes if node.asset_type == "file"}
    assert file_nodes
    assert file_nodes <= available
    clip_events = [
        event
        for event in graph.events
        if event.operator == "video.segment"
        and any(ref.asset_type == "file" for ref in event.outputs)
    ]
    assert clip_events
    for event in clip_events:
        assert event.params["immediate_source_file_id"]
        assert any(
            ref.asset_type == "file" and ref.asset_id == event.params["source_asset_id"]
            for ref in event.inputs
        )
        assert event.params["history"][-1]["operator"] == "video.invalid_frames"
