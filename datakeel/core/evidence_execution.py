# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed extraction execution context, deferred publications, and run accounting."""

from typing import Literal

from pydantic import Field

from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.models import BoundaryModel, LineageEvent


class EvidenceExecutionContext(BoundaryModel):
    """Bind one attempt to a task and the immutable manifest supplying its inputs."""

    task_id: str
    shard_id: str
    version_id: str


class PendingExtraction(BoundaryModel):
    """Defer publication until the worker proves it still owns the shard lease."""

    event: LineageEvent
    bundle: KnowledgeBundle


class ExtractionCounts(BoundaryModel):
    """Account for every input, including cache reuse and measured extraction failure."""

    inputs: int = Field(default=0, ge=0)
    skipped_cached: int = Field(default=0, ge=0)
    extracted: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0, ge=0)
    implementation: Literal["python", "rust"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    implementation_version: str | None = Field(default=None, exclude_if=lambda value: value is None)
    match_mode: Literal["prefix", "exact"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class OperatorExtractionReport(ExtractionCounts):
    """Expose one operator's reproducible incremental extraction accounting."""

    operator: str


class EvidenceRunReport(ExtractionCounts):
    """Summarize committed extraction events belonging to one durable task."""

    task_id: str
    operators: tuple[OperatorExtractionReport, ...] = ()
