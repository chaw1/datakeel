# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit, capped budgets for dataset releases and selected versions.

Ordinary controlled actions keep the default 10,000-object / 10 GiB budget. A release
or a version freezes a whole manifest, so its plan may ask for a larger budget up to a
dedicated, configurable ceiling. The requested budget is part of the frozen plan
context and therefore of the digest that a person approves.
"""

from pydantic import Field

from datakeel.actions.models import ActionContext
from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.core.settings import get_settings

LARGE_BUDGET_ACTIONS = frozenset({"publish_release", "create_version_from_selection"})
_DEFAULT = ActionContext()


class BudgetRequest(BoundaryModel):
    """Ask for an object or byte budget other than the controlled-action default."""

    max_objects: int | None = Field(default=None, ge=1)
    max_bytes: int | None = Field(default=None, ge=1)


def budget_ceiling(action_type: str) -> tuple[int, int] | None:
    """Return the configured (objects, bytes) ceiling for actions that accept explicit budgets."""
    if action_type not in LARGE_BUDGET_ACTIONS:
        return None
    settings = get_settings()
    return settings.release_budget_max_objects, settings.release_budget_max_bytes


def _ceiling_message(action_type: str, ceiling: tuple[int, int]) -> str:
    return (
        f"the {action_type} budget ceiling is {ceiling[0]} objects and {ceiling[1]} bytes; "
        "an operator can raise DATAKEEL_RELEASE_BUDGET_MAX_OBJECTS or "
        "DATAKEEL_RELEASE_BUDGET_MAX_BYTES"
    )


def _above(objects: int, size: int, ceiling: tuple[int, int]) -> bool:
    return objects > ceiling[0] or size > ceiling[1]


def requested_context(
    action_type: str, request: BudgetRequest, base: ActionContext | None = None
) -> ActionContext:
    """Bind an explicit budget into the plan context, rejecting values above the ceiling."""
    context = base or ActionContext()
    if request.max_objects is None and request.max_bytes is None:
        return context
    ceiling = budget_ceiling(action_type)
    if ceiling is None:
        accepted = ", ".join(sorted(LARGE_BUDGET_ACTIONS))
        msg = f"Explicit budgets are accepted only for {accepted}"
        raise ValidationError(msg)
    objects = context.max_objects if request.max_objects is None else request.max_objects
    size = context.max_bytes if request.max_bytes is None else request.max_bytes
    if _above(objects, size, ceiling):
        msg = (
            f"Requested budget of {objects} objects and {size} bytes is above the ceiling: "
            + _ceiling_message(action_type, ceiling)
        )
        raise ValidationError(msg)
    return context.model_copy(update={"max_objects": objects, "max_bytes": size})


def require_within_ceiling(action_type: str, context: ActionContext) -> None:
    """Refuse an explicit plan budget that no longer fits the configured ceiling.

    The default budget always stays available; the ceiling only bounds larger requests.
    """
    ceiling = budget_ceiling(action_type)
    if ceiling is None or not _above(context.max_objects, context.max_bytes, _default()):
        return
    if _above(context.max_objects, context.max_bytes, ceiling):
        msg = "Approved plan budget is above the current ceiling: " + _ceiling_message(
            action_type, ceiling
        )
        raise ValidationError(msg)


def budget_hint(action_type: str, objects: int, size: int) -> str:
    """Explain how a release or version above its plan budget can still be prepared."""
    ceiling = budget_ceiling(action_type)
    if ceiling is None:
        return ""
    if _above(objects, size, ceiling):
        return f" ({objects} objects, {size} bytes); it is also above " + _ceiling_message(
            action_type, ceiling
        )
    return (
        f" ({objects} objects, {size} bytes); prepare it again with an explicit "
        f"max_objects/max_bytes budget up to {ceiling[0]} objects and {ceiling[1]} bytes"
    )


def _default() -> tuple[int, int]:
    return _DEFAULT.max_objects, _DEFAULT.max_bytes
