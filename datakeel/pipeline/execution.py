# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute validated DAG layers and deliver observations on the caller thread."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from datakeel.core.errors import ExecutionError
from datakeel.core.media_metadata import FAILURE_KEY
from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY, OperatorResult
from datakeel.pipeline.defaults import default_pipeline
from datakeel.pipeline.models import ConditionParams, Node, Pipeline, PipelineObservation
from datakeel.pipeline.validation import reference, validate_pipeline

SlotFiles = dict[str, list[FileItem]]
OperatorExecutor = Callable[[Node, list[FileItem], Path], OperatorResult]
logger = logging.getLogger(__name__)


def _execute_node(node: Node, selected: list[FileItem], output: Path) -> SlotFiles:
    if node.kind == "condition":
        params = ConditionParams.model_validate(node.params)
        condition = len(selected) >= params.min_count and (
            params.max_count is None or len(selected) <= params.max_count
        )
        return {"true": selected if condition else [], "false": [] if condition else selected}
    if node.kind == "route":
        tables = [
            file
            for file in selected
            if file.modality == "table"
            and Path(file.filename).suffix.lower() in {".csv", ".tsv", ".parquet", ".pq"}
        ]
        table_ids = {file.id for file in tables}
        return {
            "image": [file for file in selected if file.modality == "image"],
            "text": [file for file in selected if file.modality == "text"],
            "audio": [file for file in selected if file.modality == "audio"],
            "video": [file for file in selected if file.modality == "video"],
            "table": tables,
            "other": [
                file
                for file in selected
                if file.modality not in {"image", "text", "audio", "video"}
                and file.id not in table_ids
            ],
        }
    operator = REGISTRY[str(node.operator)]
    result = operator.run(selected, output / node.id, node.params)
    return {"files": result.files}


def _observation(
    node: Node,
    selected: list[FileItem],
    output: list[FileItem],
    quality: dict[str, Any],
    error: Exception | None = None,
) -> PipelineObservation:
    if error:
        quality = {
            "issues": [{"code": "execution_failed", "severity": "critical", "message": str(error)}]
        }
    failed = error is None and _every_recording_failed(output, quality)
    if failed:
        reasons = sorted({str(file.metadata[FAILURE_KEY].get("reason", "")) for file in output})
        message = "Every recording failed: " + "; ".join(reasons)
        quality = {
            **quality,
            "issues": [{"code": "media_failed", "severity": "critical", "message": message}],
        }
    return PipelineObservation(
        node_id=node.id,
        operator=str(node.operator),
        params=(
            node.params
            if str(node.operator).startswith("custom.")
            else REGISTRY[str(node.operator)].params_type.model_validate(node.params).model_dump()
        ),
        input_count=len(selected),
        inputs=[file.id for file in selected],
        output_count=len(output),
        outputs=[file.id for file in output],
        quality=quality,
        run_state="FAILED" if error or failed else "COMPLETED",
    )


def _every_recording_failed(output: list[FileItem], quality: dict[str, Any]) -> bool:
    """Report a media node that failed recordings itself and has no healthy output.

    Isolated media operators pass failed recordings on instead of raising, so a node
    whose every recording failed is audited as failed while the task decides the rest.
    """
    return bool(quality.get("failed_files")) and all(
        isinstance(file.metadata.get(FAILURE_KEY), dict) for file in output
    )


def _operator_node(
    node: Node,
    selected: list[FileItem],
    output: Path,
    operator_executor: OperatorExecutor | None,
) -> tuple[SlotFiles, dict[str, Any]]:
    if node.kind != "operator":
        return _execute_node(node, selected, output), {}
    if str(node.operator).startswith("custom.") and operator_executor is None:
        msg = "Custom operators require the approved sandbox worker executor"
        raise ExecutionError(msg)
    result = (
        operator_executor(node, selected, output / node.id)
        if operator_executor is not None
        else REGISTRY[str(node.operator)].run(selected, output / node.id, node.params)
    )
    return {"files": result.files}, result.quality


def _run_layer(
    layer: list[Node],
    outputs: dict[str, SlotFiles],
    output_dir: Path,
    pool: ThreadPoolExecutor,
    on_event: Callable[[PipelineObservation], None] | None,
    operator_executor: OperatorExecutor | None,
) -> None:
    selected = {
        node.id: [
            file.model_copy(deep=True)
            for file in outputs[reference(node.inputs["files"])[0]][
                reference(node.inputs["files"])[1]
            ]
        ]
        for node in layer
    }
    futures = {
        node.id: pool.submit(_operator_node, node, selected[node.id], output_dir, operator_executor)
        for node in layer
    }
    failures: list[Exception] = []
    for node in layer:
        try:
            result, quality = futures[node.id].result()
        except Exception as error:
            logger.exception("Pipeline node failed")
            if node.kind == "operator" and on_event:
                on_event(_observation(node, selected[node.id], [], {}, error))
            failures.append(error)
            continue
        outputs[node.id] = result
        if node.kind == "operator" and on_event:
            on_event(_observation(node, selected[node.id], result["files"], quality))

    if failures:
        raise failures[0]


def run_pipeline(
    files: list[FileItem],
    output_dir: Path,
    pipeline: Pipeline | dict[str, Any] | None = None,
    on_event: Callable[[PipelineObservation], None] | None = None,
    operator_executor: OperatorExecutor | None = None,
) -> list[FileItem]:
    """Run independent nodes concurrently and publish only declared output slots."""
    specification, layers = validate_pipeline(
        pipeline if pipeline is not None else default_pipeline()
    )
    outputs: dict[str, SlotFiles] = {"$input": {"files": files}}
    with ThreadPoolExecutor(
        max_workers=specification.max_workers, thread_name_prefix="pipeline"
    ) as pool:
        for layer in layers:
            _run_layer(layer, outputs, Path(output_dir), pool, on_event, operator_executor)
    merged: dict[str, FileItem] = {}
    for value in specification.outputs:
        source, slot = reference(value)
        merged.update({file.id: file for file in outputs[source][slot]})
    return list(merged.values())
