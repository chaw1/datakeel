# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable inputs and reviewable results for local public repository exports."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from datakeel.core.errors import DatakeelError
from datakeel.core.models import BoundaryModel
from scripts.public_scan_models import ScanFinding


class ExportError(DatakeelError):
    """Reject unsafe destinations, invalid policies, or failed export commands."""


class ExportOptions(BoundaryModel):
    """Select a local source revision and a new destination without changing the source."""

    source: Path
    out: Path
    mode: Literal["history", "snapshot"] = "history"
    ref: str = "main"
    policy_dir: Path | None = None


class ExportPolicy(BoundaryModel):
    """Snapshot reviewed path, content, and commit-message rewrite rules."""

    excluded_patterns: tuple[str, ...]
    replacements: str
    messages: dict[str, str]


class MessageRewrite(BoundaryModel):
    """Connect an original message rewrite to its filtered commit, or its deletion."""

    original_commit: str
    filtered_commit: str | None
    message: str


class ExportReport(BoundaryModel):
    """Account for rewritten history and preserve every scanner finding for inspection."""

    schema_version: Literal[1] = 1
    mode: Literal["history", "snapshot"]
    source_ref: str
    source_commit: str | None = None
    source_commit_count: int | None = Field(default=None, ge=0)
    deleted_empty_commit_count: int | None = Field(default=None, ge=0)
    retained_commit_count: int | None = Field(default=None, ge=0)
    collapsed_commit_count: int = Field(default=0, ge=0)
    rewritten_messages: tuple[MessageRewrite, ...] = ()
    findings: tuple[ScanFinding, ...] = ()
    images: tuple[str, ...] = ()
    scanned_commits: int = 0
    errors: tuple[str, ...] = ()
    success: bool = False

    @model_validator(mode="after")
    def validate_accounting(self) -> ExportReport:
        """Require complete accounting and scan coverage whenever export produced a history."""
        if self.source_commit_count is not None:
            if self.deleted_empty_commit_count is None or self.retained_commit_count is None:
                msg = "Completed exports require every commit count"
                raise ValueError(msg)
            total = (
                self.deleted_empty_commit_count
                + self.retained_commit_count
                + self.collapsed_commit_count
            )
            if (
                total != self.source_commit_count
                or self.scanned_commits != self.retained_commit_count
            ):
                msg = "Export commit counts and complete scan coverage must reconcile"
                raise ValueError(msg)
        if self.success and (self.errors or self.findings or self.source_commit_count is None):
            msg = "Successful exports require complete evidence and no findings or errors"
            raise ValueError(msg)
        return self
