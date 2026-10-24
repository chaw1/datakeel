# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Categorized failures for individual extraction blocks."""

from datakeel.core.errors import ExecutionError, ProviderError
from datakeel.core.harness_models import TokenUsage


class ExtractionProviderError(ProviderError):
    """Retain billed usage when a completed provider response cannot be consumed."""

    def __init__(self, reason: str, *, observed_usage: TokenUsage | None = None) -> None:
        """Carry only validated usage and a safe category across the adapter boundary."""
        super().__init__(reason)
        self.observed_usage = observed_usage


class KGExtractionError(ExecutionError):
    """Expose a safe failure category without persisting sensitive provider bodies."""

    def __init__(self, reason: str, *, observed_usage: TokenUsage | None = None) -> None:
        """Record the classified reason for a failed and retryable block."""
        super().__init__(f"Graph extraction block failed: {reason}")
        self.reason = reason
        self.observed_usage = observed_usage
