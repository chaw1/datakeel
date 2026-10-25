# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Categorized transcription failures retain available usage for settlement."""

from datakeel.core.errors import ExecutionError
from datakeel.core.transcription_models import TranscriptionIssue, TranscriptionResult


class TranscriptionFailure(ExecutionError):  # noqa: N818  # Public failed-block boundary.
    """Report a failed image without discarding the observed provider response."""

    def __init__(self, reason: TranscriptionIssue, result: TranscriptionResult) -> None:
        """Retain the safe reason and complete typed result for reporting and billing."""
        super().__init__(f"Image transcription failed: {reason}: {result.error or reason}")
        self.reason = reason
        self.result = result
