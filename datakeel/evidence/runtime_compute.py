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
from datakeel.operators import REGISTRY
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
) -> dict[str, FileItem]:
    operator = REGISTRY[str(node.operator)]
    missing = [file for file in files if file.id not in hits]
    selected = files if node.operator == "evidence.near_duplicate" else missing
    output = operator.run(selected, directory, node.params).files if missing else []
    expected = {file.id for file in selected}
    if missing and (len(output) != len(expected) or {file.id for file in output} != expected):
        msg = "Evidence operators must retain exactly one output for every source sample"
        raise ExecutionError(msg)
    return {file.id: file for file in output}


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
    computed = _execute_misses(node, files, directory, hits)
    outputs: list[FileItem] = []
    entries: list[EvidenceCacheEntry] = []
    drafts: list[ObservationDraft] = []
    failed = 0
    for file in files:
        if file.id in hits:
            current = file.model_copy(
                update={
                    "metadata": {
                        **file.metadata,
                        **hits[file.id].output,
                        "evidence_failed": False,
                    }
                }
            )
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
        outputs.append(
            current.model_copy(
                update={
                    "metadata": {
                        **current.metadata,
                        "evidence_drafts": [],
                    }
                }
            )
        )
    return NodeExtraction(
        files=outputs,
        entries=tuple(entries),
        drafts=tuple(drafts),
        counts=ExtractionCounts(
            inputs=len(files),
            skipped_cached=len(hits),
            failed=failed,
            extracted=len(files) - len(hits) - failed,
        ),
    )
