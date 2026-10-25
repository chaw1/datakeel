# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Categorized transcription failures retain available usage for settlement."""

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.transcription_models import TranscriptionIssue, TranscriptionResult


class TranscriptionFailure(ExecutionError):  # noqa: N818  # Public failed-block boundary.
    """Report a failed image without discarding the observed provider response."""

    def __init__(self, reason: TranscriptionIssue, result: TranscriptionResult) -> None:
        """Retain the safe reason and complete typed result for reporting and billing."""
        super().__init__(f"Image transcription failed: {reason}: {result.error or reason}")
        self.reason: TranscriptionIssue = reason
        self.result = result


class TranscriptionUnavailableError(ValidationError):
    """Classify an image-local prerequisite failure without fabricating model output."""

    def __init__(self, message: str, *, reason: TranscriptionIssue) -> None:
        """Expose only a safe category and actionable local explanation."""
        super().__init__(message)
        self.reason: TranscriptionIssue = reason
