# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable recovery-package documents with explicit file integrity and provenance."""

from typing import Literal

from datakeel.core.models import BoundaryModel
from datakeel.versioning.models import DatabaseStatus


class RecoveryFile(BoundaryModel):
    """Bind one package-relative path to its complete bytes."""

    path: str
    sha256: str
    size: int


class RecoveryManifest(BoundaryModel):
    """Bind the actual SQLite snapshot, object copies and non-secret configuration."""

    format_version: Literal[1] = 1
    campaign: str
    source_identity: str
    source: DatabaseStatus
    source_facts: str
    target_checksums: tuple[str, ...]
    program_version: str
    sqlite_version: str
    database: RecoveryFile
    objects: tuple[RecoveryFile, ...]
    config: RecoveryFile
    credential_references: tuple[str, ...]
