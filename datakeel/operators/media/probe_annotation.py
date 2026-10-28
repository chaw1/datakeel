# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Annotate probed stream properties and a truncated file as an explicit issue."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.media_models import MediaInterval
from datakeel.operators.base import annotate

if TYPE_CHECKING:
    from datakeel.core.media_models import MediaProbe
    from datakeel.core.models import FileItem

TRUNCATED = "truncated_file"


def truncation(probe: MediaProbe) -> MediaInterval | None:
    """Return the missing tail of a file whose header promises more than it stores.

    The interval runs from the actual readable duration to the declared one, so
    reports show how much of the recording is lost and where it would have been.
    """
    if probe.declared_duration_ms is None or probe.declared_duration_ms <= probe.duration_ms:
        return None
    return MediaInterval(
        code=TRUNCATED,
        start_ms=probe.duration_ms,
        end_ms=probe.declared_duration_ms,
        severity="critical",
    )


def annotate_probe(file: FileItem, probe: MediaProbe) -> FileItem:
    """Store the probe and replace only a previous truncation issue on the recording."""
    issues = [
        MediaInterval.model_validate(value)
        for value in file.metadata.get("media_issues", [])
        if value.get("code") != TRUNCATED
    ]
    missing = truncation(probe)
    if missing is not None:
        issues.append(missing)
    return annotate(
        file,
        media_probe=probe.model_dump(mode="json"),
        media_issues=[issue.model_dump(mode="json") for issue in issues],
    )
