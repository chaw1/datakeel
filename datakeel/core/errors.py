# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Domain failures translated once at each application boundary."""

from http import HTTPStatus


class DatakeelError(Exception):
    """Base class for an expected application failure."""


class ValidationError(DatakeelError, ValueError):
    """An input violates a domain invariant."""


class NotFoundError(DatakeelError, LookupError):
    """A referenced asset does not exist."""


class ConflictError(DatakeelError):
    """An operation conflicts with the current persisted state."""


class AuthorizationError(DatakeelError):
    """An actor lacks the required scope or approval."""


class BudgetError(DatakeelError):
    """An operation would exceed a persistent resource budget."""


class ExecutionError(DatakeelError, RuntimeError):
    """An execution could not produce its declared result."""


class ProviderError(ValidationError):
    """Preserve provider failure classification without exposing a framework exception."""

    def __init__(self, reason: str, *, status_code: int | None = None) -> None:
        """Keep error categories and HTTP status separate from potentially sensitive bodies."""
        super().__init__("Model provider request failed")
        self.reason = reason
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        """Allow only explicitly bounded transient provider failures to trigger fallback."""
        return (
            self.reason == "timeout"
            or self.status_code == HTTPStatus.TOO_MANY_REQUESTS
            or (
                self.status_code is not None
                and HTTPStatus.INTERNAL_SERVER_ERROR
                <= self.status_code
                < HTTPStatus.INTERNAL_SERVER_ERROR + 100
            )
        )
