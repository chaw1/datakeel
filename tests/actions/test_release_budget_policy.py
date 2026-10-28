# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit budgets stay bounded without taking the default budget away."""

import pytest

from datakeel.actions.budget import (
    BudgetRequest,
    budget_hint,
    requested_context,
    require_within_ceiling,
)
from datakeel.actions.models import ActionContext
from datakeel.core.errors import ValidationError


def test_no_request_keeps_the_default_context() -> None:
    """Omitting both values leaves every action on the ordinary default budget."""
    base = ActionContext(actor="reviewer")
    assert requested_context("delete_files", BudgetRequest(), base) is base
    assert requested_context("publish_release", BudgetRequest()) == ActionContext()


def test_partial_request_keeps_the_other_default() -> None:
    """A byte-only request keeps the default object budget and vice versa."""
    context = requested_context("create_version_from_selection", BudgetRequest(max_bytes=2**40))
    assert (context.max_objects, context.max_bytes) == (10000, 2**40)


def test_lowered_ceiling_never_blocks_the_default_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ceiling bounds explicit requests; default plans remain valid."""
    monkeypatch.setenv("DATAKEEL_RELEASE_BUDGET_MAX_OBJECTS", "5")
    require_within_ceiling("publish_release", ActionContext())
    with pytest.raises(ValidationError, match="current ceiling"):
        require_within_ceiling("publish_release", ActionContext(max_objects=20_000))
    require_within_ceiling("delete_files", ActionContext(max_objects=20_000))


def test_hint_names_the_ceiling_or_the_explicit_budget() -> None:
    """Ordinary actions get no hint; releases explain the next step."""
    assert budget_hint("delete_files", 20_000, 1) == ""
    assert "max_objects" in budget_hint("publish_release", 20_000, 1)
    assert "DATAKEEL_RELEASE_BUDGET_MAX_OBJECTS" in budget_hint("publish_release", 2_000_000, 1)
