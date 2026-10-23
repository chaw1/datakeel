# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Lineage ancestry collapses control nodes without losing source identity."""

from datakeel.pipeline import Node, Pipeline, PipelineObservation
from datakeel.storage.task_queue import Lease
from datakeel.worker.observations import Observations


def test_control_node_ancestry_resolves_to_original_source() -> None:
    """Verify control node ancestry resolves to original source."""
    lease = Lease(
        shard_id="shard", task_id="task", dataset_id="data", owner="owner", inputs=[], pipeline=None
    )
    definition = Pipeline(
        nodes=[Node(id="route", kind="route", inputs={"files": "$input.files"})],
        outputs=["route.text"],
    )
    observations = Observations(lease, definition)
    assert [ref.asset_id for ref in observations.ancestors("route.text")] == ["data"]


def test_failed_operator_records_evidence_without_claiming_artifact_output() -> None:
    """Verify failed operator records evidence without claiming artifact output."""
    lease = Lease(
        shard_id="shard", task_id="task", dataset_id="data", owner="owner", inputs=[], pipeline=None
    )
    definition = Pipeline(
        nodes=[Node(id="inspect", operator="file.empty_check", inputs={"files": "$input.files"})],
        outputs=["inspect.files"],
    )
    observations = Observations(lease, definition)
    observations.observe(
        PipelineObservation(
            node_id="inspect",
            operator="file.empty_check",
            params={},
            input_count=1,
            inputs=["source"],
            output_count=0,
            outputs=[],
            quality={},
            run_state="FAILED",
        )
    )
    event = observations.events[0]
    assert event.run_state == "FAILED"
    assert event.outputs == []
    assert [ref.asset_id for ref in event.inputs] == ["data"]
