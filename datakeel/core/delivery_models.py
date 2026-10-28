# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable delivery manifests and independent reconciliation receipts."""

from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel, new_id, utcnow

CheckName = Literal["file_count", "bytes", "hashes", "annotations", "metadata", "lineage"]


class DeliveryFile(BoundaryModel):
    """Register one public payload and the facts its recipient must verify."""

    path: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str
    source_version: str
    lineage_refs: tuple[str, ...]
    annotation_count: int = Field(ge=0)
    label_count: int = Field(ge=0)
    required_metadata: tuple[str, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DeliveryLineage(BoundaryModel):
    """Identify one source version without revealing internal object locations."""

    version_id: str
    dataset_id: str


class DeliveryManifest(BoundaryModel):
    """Versioned, self-contained contract for a release delivery."""

    format_version: Literal["1.0"] = "1.0"
    release_id: str
    tag: str
    dataset_id: str
    source_version: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    required_metadata: tuple[str, ...] = ()
    files: tuple[DeliveryFile, ...]
    lineage: tuple[DeliveryLineage, ...]
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeliveryRecord(BoundaryModel):
    """Independent receipt-side metadata, statistics and ancestry for one payload."""

    path: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    annotation_count: int = Field(ge=0)
    label_count: int = Field(ge=0)
    source_version: str
    lineage_refs: tuple[str, ...]


class DeliveryRecords(BoundaryModel):
    """Keep receipt-side records distinct from the expected manifest."""

    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    files: tuple[DeliveryRecord, ...]


class Difference(BoundaryModel):
    """Explain one failed check with machine-readable expected and actual values."""

    path: str
    expected: JsonValue = None
    actual: JsonValue = None
    reason: str


class CheckResult(BoundaryModel):
    """Report one of the six independent reconciliation categories."""

    name: CheckName
    passed: bool
    differences: tuple[Difference, ...] = ()


class ReconcileReport(BoundaryModel):
    """Archive a complete offline or platform-side verification result."""

    id: str = Field(default_factory=new_id)
    release_id: str | None = None
    created_at: float = Field(default_factory=lambda: utcnow().timestamp())
    passed: bool
    categories: tuple[CheckResult, ...]
