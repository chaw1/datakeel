# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Domain failures translated once at each application boundary."""


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
