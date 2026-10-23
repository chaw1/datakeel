# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable, value-redacted evidence from public repository history scans."""

from pydantic import Field

from datakeel.core.models import BoundaryModel


class LineFinding(BoundaryModel):
    """Identify a rule and line without copying potentially sensitive source values."""

    line: int = Field(ge=1)
    rule: str


class ScanFinding(LineFinding):
    """Locate one finding in a specific historical commit and file or metadata field."""

    commit: str
    path: str


class BlobScan(BoundaryModel):
    """Cache content results independently of each historical occurrence."""

    findings: tuple[LineFinding, ...]
    image: bool = False


class ScanReport(BoundaryModel):
    """Report every occurrence, all historical image paths, and traversal counts."""

    findings: tuple[ScanFinding, ...]
    images: tuple[str, ...]
    scanned_commits: int = Field(ge=0)
    scanned_blobs: int = Field(ge=0)
