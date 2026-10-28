# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reuse per-sample metadata patches and execute only invalidated extractor inputs."""

from pathlib import Path

from pydantic import JsonValue

from datakeel.core.errors import ExecutionError
from datakeel.core.evidence_cache import EvidenceCacheEntry
from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_execution import ExtractionCounts
from datakeel.core.models import BoundaryModel, FileItem, JsonDocument
from datakeel.operators import REGISTRY, OperatorResult
from datakeel.pipeline.models import Node

_CONTEXT_KEYS = {"evidence_drafts", "evidence_subject", "evidence_sample"}


class NodeExtraction(BoundaryModel):
    """Carry an executed node's output, cache updates, and uncommitted observations."""

    files: list[FileItem]
    entries: tuple[EvidenceCacheEntry, ...]
    drafts: tuple[ObservationDraft, ...]
    counts: ExtractionCounts


def _patch(before: FileItem, after: FileItem) -> dict[str, JsonValue]:
    return JsonDocument.model_validate(
        {
            key: value
            for key, value in after.metadata.items()
            if key not in _CONTEXT_KEYS
            and (key not in before.metadata or before.metadata[key] != value)
        }
    ).root


def _execute_misses(
    node: Node, files: list[FileItem], directory: Path, hits: dict[str, EvidenceCacheEntry]
) -> OperatorResult:
    operator = REGISTRY[str(node.operator)]
    missing = [file for file in files if file.id not in hits]
    selected = files if node.operator == "evidence.near_duplicate" else missing
    result = (
        operator.run(selected if missing else [], directory, node.params)
        if missing or node.operator == "evidence.near_duplicate"
        else OperatorResult(files=[])
    )
    output = result.files
    expected = {file.id for file in selected}
    if missing and (len(output) != len(expected) or {file.id for file in output} != expected):
        msg = "Evidence operators must retain exactly one output for every source sample"
        raise ExecutionError(msg)
    return result


def _restore(file: FileItem, cached: EvidenceCacheEntry) -> FileItem:
    return file.model_copy(
        update={"metadata": {**file.metadata, **cached.output, "evidence_failed": False}}
    )


def _reporting(result: OperatorResult) -> dict[str, JsonValue]:
    return JsonDocument.model_validate(
        {
            key: result.quality[key]
            for key in ("implementation", "implementation_version", "match_mode")
            if key in result.quality
        }
    ).root


def _output(file: FileItem, implementation: dict[str, JsonValue]) -> FileItem:
    metadata = {
        f"near_duplicate_{key.removeprefix('match_')}": value
        for key, value in implementation.items()
    }
    return file.model_copy(
        update={"metadata": {**file.metadata, "evidence_drafts": [], **metadata}}
    )


def compute_node(
    node: Node,
    files: list[FileItem],
    directory: Path,
    requests: tuple[EvidenceCacheEntry, ...],
    cached: tuple[EvidenceCacheEntry, ...],
) -> NodeExtraction:
    """Return typed node observations without writing events or cache projections."""
    hits = {entry.subject.asset_id: entry for entry in cached}
    requests_by_id = {entry.subject.asset_id: entry for entry in requests}
    result = _execute_misses(node, files, directory, hits)
    computed = {file.id: file for file in result.files}
    implementation = _reporting(result)
    outputs: list[FileItem] = []
    entries: list[EvidenceCacheEntry] = []
    drafts: list[ObservationDraft] = []
    failed = 0
    for file in files:
        if file.id in hits:
            current = _restore(file, hits[file.id])
        else:
            current = computed[file.id]
            failed += int(current.metadata.get("evidence_failed") is True)
            drafts.extend(
                ObservationDraft.model_validate(value)
                for value in current.metadata.get("evidence_drafts", [])
            )
            entries.append(
                requests_by_id[file.id].model_copy(update={"output": _patch(file, current)})
            )
        outputs.append(_output(current, implementation))
    return NodeExtraction(
        files=outputs,
        entries=tuple(entries),
        drafts=tuple(drafts),
        counts=ExtractionCounts.model_validate(
            {
                "inputs": len(files),
                "skipped_cached": len(hits),
                "failed": failed,
                "extracted": len(files) - len(hits) - failed,
                **implementation,
            }
        ),
    )
