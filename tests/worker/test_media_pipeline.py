# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real generated media through durable publication, retries and cancellation fencing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.cli.media_demo import run_demo
from datakeel.core.media_models import MediaSummary
from datakeel.pipeline import Node, Pipeline, run_pipeline
from datakeel.pipeline.media import media_pipeline
from datakeel.storage.dataset_service import import_paths, list_versions, task_artifacts
from datakeel.storage.lineage_service import get_graph
from datakeel.storage.task_queries import query_task
from datakeel.worker.observations import Observations
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_generated_media_report_and_rerun_keep_exact_lineage(db: Database) -> None:
    """The production queue publishes measured originals, clean clips and stable reruns."""
    result = run_demo(db)
    dataset_id, task_id = str(result["dataset_id"]), str(result["task_id"])
    summary = MediaSummary.model_validate(result["quality"]["media"])
    assert summary.clip_count > 0
    assert 0 < summary.effective_duration_ms < summary.original_duration_ms
    assert summary.original_duration_ms == 36500
    assert summary.duplicate_count > 0
    assert {"black_frame", "frozen_frame", "video_duplicate", "audio_silence"} <= set(
        summary.issue_distribution
    )
    assert "Original duration:" in result["report"]["body"]
    outputs = task_artifacts(db, task_id)
    clips = [
        file
        for file in outputs
        if file.media and any(step.operator == "video.segment" for step in file.media.history)
    ]
    assert clips
    for clip in clips:
        assert clip.media is not None
        graph = get_graph(db, clip.id, direction="upstream")
        events = [event for event in graph.events if event.operator == "video.segment"]
        assert events
        assert events[0].params["operator_version"] == "1.0.0"
        assert events[0].params["end_ms"] > events[0].params["start_ms"]
        assert clip.media.source_asset_id in {node.asset_id for node in graph.nodes}
        assert {
            "video.probe",
            "video.invalid_frames",
            "video.dedup",
            "video.normalize",
            "video.segment",
        } <= {step.operator for step in clip.media.history}
    queue = DatabaseQueue(db)
    rerun = queue.submit(dataset_id, "generated-media-rerun", media_pipeline(align=True))
    assert queue.submit(dataset_id, "generated-media-rerun", media_pipeline(align=True)) == rerun
    run_worker(db, once=True)
    assert query_task(db, rerun).state == "COMPLETED"
    assert [(item.id, item.sha256) for item in task_artifacts(db, rerun)] == [
        (item.id, item.sha256) for item in outputs
    ]
    assert queue.relay() == 0
    assert len(list_versions(db, dataset_id)) == 3


def test_cancelled_media_attempt_cannot_publish_artifacts_or_lineage(
    db: Database, tmp_path: Path
) -> None:
    """A cancelled attempt leaves no derived manifest or transformation events."""
    from datakeel.operators.media.tools import run_tool  # noqa: PLC0415  # Local generated fixture.

    path = tmp_path / "generated.mp4"
    run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=96x64:r=30:d=0.4",
            "-c:v",
            "mpeg4",
            str(path),
        ]
    )
    dataset = import_paths(db, "Generated cancellation", [path])
    definition = Pipeline(
        nodes=[
            Node(id="route", kind="route", inputs={"files": "$input.files"}),
            Node(
                id="segment",
                operator="video.segment",
                inputs={"files": "route.video"},
                params={"window_ms": 200},
            ),
        ],
        outputs=["segment.files"],
    )
    queue = DatabaseQueue(db)
    task_id = queue.submit(dataset.id, "cancelled-media", definition)
    lease = queue.claim()
    assert lease is not None
    assert lease.pipeline is not None
    observations = Observations(lease, lease.pipeline)
    outputs = run_pipeline(lease.inputs, tmp_path / "attempt", lease.pipeline, observations.observe)
    assert outputs
    assert observations.events
    assert queue.cancel(task_id)
    assert not queue.finish(lease, outputs, observations.events)
    assert len(list_versions(db, dataset.id)) == 1
    assert not any(event.operator == "video.segment" for event in get_graph(db, dataset.id).events)
    assert queue.relay() == 1
    assert queue.relay() == 0


def test_single_recording_uses_media_pipeline_without_alignment(
    db: Database, tmp_path: Path
) -> None:
    """A single recording can complete preprocessing without inventing a second input."""
    from datakeel.operators.media.tools import run_tool  # noqa: PLC0415  # Local generated fixture.

    path = tmp_path / "single.wav"
    run_tool(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=0.5", str(path)])
    dataset = import_paths(db, "Generated single recording", [path])
    task_id = DatabaseQueue(db).submit(dataset.id, "single-media", media_pipeline())
    run_worker(db, once=True)
    assert query_task(db, task_id).state == "COMPLETED"
    assert task_artifacts(db, task_id)
    assert not any(event.operator == "media.align" for event in get_graph(db, dataset.id).events)


def test_duplicate_audio_keeps_source_duration_in_report(db: Database, tmp_path: Path) -> None:
    """Retain both measured originals while publishing only one cleaned audio copy."""
    from datakeel.operators.media.tools import run_tool  # noqa: PLC0415  # Local generated fixture.
    from datakeel.quality import score_quality  # noqa: PLC0415  # Direct report assertion.
    from datakeel.storage.datasets import materialize_files  # noqa: PLC0415  # Typed stored files.

    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    run_tool(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(first)])
    second.write_bytes(first.read_bytes())
    dataset = import_paths(db, "Generated duplicate audio", [first, second])
    task_id = DatabaseQueue(db).submit(dataset.id, "duplicate-audio-report", media_pipeline())
    run_worker(db, once=True)
    assert query_task(db, task_id).state == "COMPLETED"
    artifacts = task_artifacts(db, task_id)
    from datakeel.core.models import FileItem  # noqa: PLC0415  # Typed file conversion.

    items = [FileItem(path="", **file.model_dump(exclude={"media"})) for file in artifacts]
    quality = score_quality(materialize_files(items))
    assert quality.media is not None
    assert quality.media.original_duration_ms == 2000
    assert quality.media.duplicate_count == 1
    assert (
        len([file for file in artifacts if file.media and file.media.source_file_id is None]) == 2
    )
    assert (
        len([file for file in artifacts if file.media and file.media.source_file_id is not None])
        == 1
    )
