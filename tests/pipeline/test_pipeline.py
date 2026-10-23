# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for pipeline."""

from __future__ import annotations

import threading
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

import numpy as np
import pytest
from PIL import Image

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.base import summarize
from datakeel.pipeline import default_pipeline, run_pipeline, validate_pipeline

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Never, NotRequired

    from pydantic import JsonValue

    from datakeel.operators.base import OperatorResult, Params


class PipelineDocument(TypedDict):
    """Describe the intentionally mutable JSON document used for invalid DAG cases."""

    nodes: list[dict[str, JsonValue]]
    outputs: list[str]
    max_workers: NotRequired[int]


def file_at(tmp_path: Path, name: str, content: bytes, modality: str) -> FileItem:
    """Provide the file at test fixture."""
    path = tmp_path / name
    path.write_bytes(content)
    return FileItem(path=str(path), filename=name, modality=modality, size=len(content))


def test_default_executes_all_operators_and_events(tmp_path: Path) -> None:
    """Verify default executes all operators and events."""
    buffer = BytesIO()
    Image.fromarray(np.full((100, 200, 3), 90, dtype=np.uint8)).save(buffer, format="PNG")
    files = [
        file_at(tmp_path, "sample.png", buffer.getvalue(), "image"),
        file_at(
            tmp_path,
            "sample.txt",
            b"Generated text contact sample@example.org with reference 42.",
            "text",
        ),
    ]
    events = []
    output = run_pipeline(files, tmp_path / "output", on_event=events.append)
    assert len(events) == 11
    assert {event["operator"] for event in events} == {
        node.operator for node in default_pipeline().nodes if node.kind == "operator"
    }
    assert all(
        event["run_state"] == "COMPLETED" and "issues" in event["quality"] for event in events
    )
    assert len(output) == 2
    assert all(Path(file.path).is_file() for file in output)
    assert all(file.metadata == {} for file in files)
    assert "@" not in next(
        Path(file.path).read_text() for file in output if file.modality == "text"
    )
    assert all(
        {"inputs", "outputs", "node_id", "params", "input_count", "output_count"} <= event.keys()
        for event in events
    )


def test_same_layer_is_parallel_and_events_use_caller_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify same layer is parallel and events use caller thread."""
    barrier = threading.Barrier(2, timeout=3)
    threads = []

    def execute(files: list[FileItem], _output_dir: Path, _params: Params) -> OperatorResult:
        """Provide the execute test fixture."""
        threads.append(threading.get_ident())
        barrier.wait()
        return summarize(files, files)

    monkeypatch.setattr(REGISTRY["file.empty_check"], "execute", execute)
    monkeypatch.setattr(REGISTRY["file.corrupt_check"], "execute", execute)
    definition = {
        "nodes": [
            {"id": "a", "operator": "file.empty_check", "inputs": {"files": "$input.files"}},
            {"id": "b", "operator": "file.corrupt_check", "inputs": {"files": "$input.files"}},
        ],
        "outputs": ["a.files", "b.files"],
        "max_workers": 2,
    }
    callbacks = []
    run_pipeline([], tmp_path, definition, lambda _event: callbacks.append(threading.get_ident()))
    assert len(set(threads)) == 2
    assert callbacks == [threading.get_ident(), threading.get_ident()]


def test_condition_false_and_modality_routes(tmp_path: Path) -> None:
    """Verify condition false and modality routes."""
    files = [
        file_at(tmp_path, "text.txt", b"text", "text"),
        file_at(tmp_path, "other.bin", b"data", "unknown"),
    ]
    definition = {
        "nodes": [
            {
                "id": "gate",
                "kind": "condition",
                "inputs": {"files": "$input.files"},
                "params": {"min_count": 3},
            },
            {"id": "route", "kind": "route", "inputs": {"files": "gate.false"}},
        ],
        "outputs": ["route.text", "route.other", "gate.true"],
    }
    assert {file.id for file in run_pipeline(files, tmp_path / "output", definition)} == {
        file.id for file in files
    }
    definition["outputs"] = ["route.image", "gate.true"]
    assert run_pipeline(files, tmp_path / "output", definition) == []


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["nodes"][0].update(operator="unknown"),
        lambda d: d["nodes"][0].update(inputs={"files": "absent.files"}),
        lambda d: d["nodes"][0].update(inputs={"files": "convert.files"}),
        lambda d: d["nodes"][0].update(inputs={"wrong": "$input.files"}),
        lambda d: d["nodes"][0].update(params={"unexpected": 1}),
        lambda d: d["nodes"][0].update(id="../escape"),
        lambda d: d["nodes"][1].update(id="dedup"),
        lambda d: d["nodes"][5].update(inputs={"files": "modality.text"}),
        lambda d: d["nodes"][5].update(inputs={"files": "modality.missing"}),
        lambda d: d["nodes"][6].update(params={"width": -1}),
        lambda d: d["nodes"][5].update(params={"min_brightness": 200.0, "max_brightness": 100.0}),
        lambda d: d["nodes"][5].update(params={"blur_threshold": float("inf")}),
        lambda d: d["nodes"][4].update(params={"invalid": True}),
        lambda d: d["nodes"][3].update(params={"min_count": 4, "max_count": 2}),
        lambda d: d.update(outputs=["absent.files"]),
    ],
)
def test_invalid_dags_rejected_before_writes(
    tmp_path: Path, change: Callable[[PipelineDocument], None]
) -> None:
    """Verify invalid dags rejected before writes."""
    definition = cast("PipelineDocument", default_pipeline().model_dump())
    change(definition)
    output_dir = tmp_path / "must-not-exist"
    with pytest.raises(
        ValueError, match=r"Unknown|cycle|slots|validation|unique|Incompatible|parameters|Invalid"
    ):
        run_pipeline([], output_dir, definition)
    assert not output_dir.exists()


def test_typed_condition_preserves_image_slot(tmp_path: Path) -> None:
    """Verify typed condition preserves image slot."""
    definition = {
        "nodes": [
            {"id": "route", "kind": "route", "inputs": {"files": "$input.files"}},
            {"id": "gate", "kind": "condition", "inputs": {"files": "route.image"}},
            {"id": "resize", "operator": "image.resize", "inputs": {"files": "gate.true"}},
        ],
        "outputs": ["resize.files"],
    }
    validate_pipeline(definition)
    assert run_pipeline([], tmp_path, definition) == []


def test_failed_operator_emits_terminal_event(tmp_path: Path) -> None:
    """Verify failed operator emits terminal event."""
    missing = FileItem(path=str(tmp_path / "absent"), filename="absent.txt", modality="text")
    events = []
    with pytest.raises(OSError, match="No such file"):
        run_pipeline([missing], tmp_path / "output", on_event=events.append)
    assert len(events) == 1
    assert events[0]["run_state"] == "FAILED"
    assert events[0]["quality"]["issues"][0]["severity"] == "critical"


def test_empty_branches_emit_zero_item_events_without_artifacts(tmp_path: Path) -> None:
    """Verify empty branches emit zero item events without artifacts."""
    events = []
    assert run_pipeline([], tmp_path / "output", on_event=events.append) == []
    assert len(events) == sum(node.kind == "operator" for node in default_pipeline().nodes)
    assert all(event["input_count"] == event["output_count"] == 0 for event in events)
    assert all(event["inputs"] == event["outputs"] == [] for event in events)
    assert all(event["run_state"] == "COMPLETED" for event in events)
    assert not [path for path in (tmp_path / "output").rglob("*") if path.is_file()]


def test_false_condition_keeps_input_out_of_downstream_operators(tmp_path: Path) -> None:
    """Verify false condition keeps input out of downstream operators."""
    source = file_at(tmp_path, "text.txt", b"sample@example.org", "text")
    definition = {
        "nodes": [
            {
                "id": "gate",
                "kind": "condition",
                "inputs": {"files": "$input.files"},
                "params": {"min_count": 2},
            },
            {"id": "route", "kind": "route", "inputs": {"files": "gate.true"}},
            {"id": "redact", "operator": "text.pii_redact", "inputs": {"files": "route.text"}},
        ],
        "outputs": ["redact.files", "gate.false"],
    }
    events = []
    output = run_pipeline([source], tmp_path / "output", definition, events.append)
    assert [file.id for file in output] == [source.id]
    assert Path(output[0].path).read_bytes() == b"sample@example.org"
    assert len(events) == 1
    assert events[0]["output_count"] == events[0]["input_count"] == 0


def test_parallel_layer_retains_other_receipts_when_first_future_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify parallel layer retains other receipts when first future fails."""
    barrier = threading.Barrier(2, timeout=3)

    def fail(_files: list[FileItem], _output_dir: Path, _params: Params) -> Never:
        """Provide the fail test fixture."""
        barrier.wait()
        msg = "injected sibling failure"
        raise RuntimeError(msg)

    def succeed(files: list[FileItem], _output_dir: Path, _params: Params) -> OperatorResult:
        """Provide the succeed test fixture."""
        barrier.wait()
        return summarize(files, files)

    monkeypatch.setattr(REGISTRY["file.empty_check"], "execute", fail)
    monkeypatch.setattr(REGISTRY["file.corrupt_check"], "execute", succeed)
    definition = {
        "nodes": [
            {"id": "a", "operator": "file.empty_check", "inputs": {"files": "$input.files"}},
            {"id": "b", "operator": "file.corrupt_check", "inputs": {"files": "$input.files"}},
        ],
        "outputs": ["a.files", "b.files"],
    }
    events = []
    with pytest.raises(RuntimeError, match="injected sibling failure"):
        run_pipeline([], tmp_path, definition, events.append)
    assert [(event.node_id, event.run_state) for event in events] == [
        ("a", "FAILED"),
        ("b", "COMPLETED"),
    ]
