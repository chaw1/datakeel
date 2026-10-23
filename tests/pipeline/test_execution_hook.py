# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cache execution preserves DAG routing and terminal observations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.base import OperatorResult
from datakeel.pipeline import run_pipeline

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.pipeline import Node, PipelineObservation


def test_cached_execution_when_input_unavailable_preserves_routing_and_observations(
    tmp_path: Path,
) -> None:
    """Reuse a cached observation without re-reading bytes or bypassing the DAG."""
    source = FileItem(path=str(tmp_path / "unavailable.txt"), filename="unavailable.txt")
    definition = {
        "nodes": [
            {"id": "gate", "kind": "condition", "inputs": {"files": "$input.files"}},
            {"id": "dedup", "operator": "file.dedup", "inputs": {"files": "gate.true"}},
        ],
        "outputs": ["dedup.files"],
    }
    calls: list[str] = []
    events: list[PipelineObservation] = []

    def reuse(node: Node, files: list[FileItem], output: Path) -> OperatorResult:
        """Simulate a valid cache hit after independently checking its identity."""
        calls.append(node.id)
        assert output == tmp_path / "out" / "dedup"
        return OperatorResult(files=files, quality={"skipped_cached": len(files)})

    result = run_pipeline([source], tmp_path / "out", definition, events.append, reuse)
    assert result == [source]
    assert calls == ["dedup"]
    assert len(events) == 1
    assert events[0].run_state == "COMPLETED"
    assert events[0].quality == {"skipped_cached": 1}
    assert events[0].inputs == [source.id]


def test_cached_execution_when_hook_fails_keeps_failed_terminal_observation(
    tmp_path: Path,
) -> None:
    """Surface a cache-validation failure with the same durable failure evidence."""
    events: list[PipelineObservation] = []

    def fail(_node: Node, _files: list[FileItem], _output: Path) -> OperatorResult:
        """Reject a deliberately corrupted cached product."""
        msg = "Cached content hash mismatch"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="hash mismatch"):
        run_pipeline([], tmp_path, on_event=events.append, operator_executor=fail)
    assert events[0].run_state == "FAILED"
    assert events[0].output_count == 0
