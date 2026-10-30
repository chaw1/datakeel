# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""How a sentence ends when there is no plan, each ending under its own condition.

* ``failed``: the model call failed (timeout, HTTP status, network) or its answer stayed
  unreadable after one more try; the person hears that and why, never "unsupported".
* related actions exist: a question naming them, never "unsupported".
* ``unsupported``: nothing in the registry is related to the request.
* internal errors: a plain sentence, never the raw error text.
"""

from collections.abc import Callable

import httpx
from pydantic import ValidationError as ModelValidationError

from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.core.errors import DatakeelError, ProviderError
from datakeel.core.intent_models import Candidate, Clarification, IntentResult
from datakeel.intents.drafts import IntentDraft
from datakeel.intents.rules import full_registry
from datakeel.intents.wording import (
    internal_failure,
    model_failed,
    related_question,
    unsupported_text,
)

RELATED_LIMIT = 3


class PlannerFailure(Exception):  # noqa: N818 - it names an outcome shown to the person
    """A model call failed or its answer stayed unreadable; carries a short reason."""

    def __init__(self, reason: str) -> None:
        """Keep only a short category (timeout, http_429, unreadable), never a body."""
        super().__init__(reason)
        self.reason = reason


def _reason(error: Exception) -> str:
    if isinstance(error, ProviderError):
        return error.reason
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.HTTPStatusError):
        return f"http_{error.response.status_code}"
    if isinstance(error, httpx.HTTPError):
        return "network"
    return "provider"


def call_model(
    complete: Callable[[ModelRequest], ModelResponse], request: ModelRequest
) -> ModelResponse:
    """Ask the model once; any transport or provider failure becomes a PlannerFailure."""
    try:
        return complete(request)
    except (DatakeelError, httpx.HTTPError, ModelValidationError, ValueError) as error:
        raise PlannerFailure(_reason(error)) from error


def failed(text: str, reason: str, language: str) -> IntentResult:
    """The model call failed: say so with the reason; nothing was changed."""
    return IntentResult(kind="failed", text=model_failed(reason, language), request=text)


def internal_error(text: str, language: str) -> IntentResult:
    """An internal error while planning: a plain sentence, the raw error stays in the log."""
    return IntentResult(kind="failed", text=internal_failure(language), request=text)


def unsupported(text: str, language: str) -> IntentResult:
    """Say plainly that this is not something the platform can do, and what it can do."""
    return IntentResult(kind="unsupported", text=unsupported_text(language), request=text)


def _titles(language: str) -> dict[str, str]:
    registry = full_registry()
    entries = [*registry.actions, *registry.functions]
    titles: dict[str, str] = {}
    for entry in entries:
        groups = [group for group in entry.phrases.values() if group]
        said = entry.phrases.get(language) or (groups[0] if groups else [])
        titles[entry.id] = said[0] if said else entry.id
    return titles


def no_fit(draft: IntentDraft | None, text: str, language: str) -> IntentResult:
    """Nothing was planned: ask about related registered actions, else say unsupported."""
    titles = _titles(language)
    related = [name for name in (draft.related if draft else []) if name in titles]
    related = list(dict.fromkeys(related))[:RELATED_LIMIT]
    if not related:
        return unsupported(text, language)
    question = related_question([titles[name] for name in related], language)
    choices = [Candidate(id=name, label=titles[name], kind="action") for name in related]
    return IntentResult(
        kind="clarify",
        text=question,
        request=text,
        clarification=Clarification(question=question, candidates=choices),
    )
