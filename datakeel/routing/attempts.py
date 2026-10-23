# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit fallback scheduling over independent metered provider attempts."""

from collections.abc import Callable

from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.core.errors import ProviderError
from datakeel.core.routing_models import ModelRouteDecision
from datakeel.routing.accounting import ModelAccount


def complete_with_fallback(
    account: ModelAccount,
    request: ModelRequest,
    invoke: Callable[[ModelRequest], ModelResponse],
    route: ModelRouteDecision,
    models: list[str],
    refresh: Callable[[], ModelRequest] | None = None,
) -> ModelResponse:
    """Retry only normalized timeout, rate-limit, and server failures on configured backups."""
    reason: str | None = None
    for index, model in enumerate(models):
        if index and refresh is not None:
            request = refresh()
        selected = route.model_copy(
            update={"model": model, "attempt": index + 1, "fallback_reason": reason}
        )
        try:
            return account.complete(request.model_copy(update={"model": model}), invoke, selected)
        except ProviderError as error:
            if not error.retryable or index == len(models) - 1:
                raise
            reason = error.reason
    msg = "Model routing produced an empty attempt chain"
    raise ValueError(msg)
