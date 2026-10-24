# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Categorized failures for individual extraction blocks."""

from datakeel.core.errors import ExecutionError


class KGExtractionError(ExecutionError):
    """Expose a safe failure category without persisting sensitive provider bodies."""

    def __init__(self, reason: str) -> None:
        """Record the classified reason for a failed and retryable block."""
        super().__init__(f"Graph extraction block failed: {reason}")
        self.reason = reason
