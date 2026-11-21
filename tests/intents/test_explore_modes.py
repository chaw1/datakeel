# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-first mode selection and discovered identities survive the whole planner pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import ValidationError

from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse
from datakeel.core.intent_models import PageContext
from datakeel.core.settings import Settings
from datakeel.intents.catalog import (
    CatalogEntry,
    EntityCatalog,
    build_catalog,
    catalog_needs_explore,
)
from datakeel.intents.explore import Lookups
from datakeel.intents.planner import ModelAccess, PlannerTurn, plan_turn
from datakeel.ontology.tool_models import ToolCallContext
from tests.intents.model_support import REQUEST, PlannerProvider
from tests.intents.planning_support import steps, two_projects
from tests.intents.test_catalog_lookup import users
from tests.intents.test_read_first_explore import final, look

if TYPE_CHECKING:
    from datakeel.core.agent_models import ModelRequest
    from datakeel.storage.database import Database


@pytest.mark.parametrize(
    ("mode", "threshold", "truncated", "forced", "expected"),
    [
        ("off", 1, True, False, False),
        ("off", 5000, False, True, True),
        ("on", 5000, False, False, True),
        ("auto", 5000, True, False, True),
        ("auto", 1, False, False, True),
        ("auto", 2, False, False, False),
    ],
)
def test_mode_selection_preserves_opt_in_and_automatic_thresholds(
    mode: Literal["off", "auto", "on"],
    threshold: int,
    *,
    truncated: bool,
    forced: bool,
    expected: bool,
) -> None:
    """Auto responds to either truncation or size while the legacy flag still forces reads."""
    catalog = EntityCatalog(
        entries=[CatalogEntry(kind="user", id="u", label="User")], truncated=truncated
    )
    access = ModelAccess(explore_mode=mode, explore_threshold=threshold, explore=forced)
    assert access.explores(catalog) is expected
    assert catalog_needs_explore(catalog, threshold=threshold) is (truncated or threshold <= 1)
    assert ModelAccess().explore_mode == "off"


@pytest.mark.parametrize("threshold", [0, 5001])
def test_production_settings_bound_explore_threshold(threshold: int) -> None:
    """Production auto mode is default and invalid catalog thresholds fail configuration."""
    assert Settings().intent_planner_explore == "auto"
    assert Settings().intent_planner_explore_threshold == 60
    with pytest.raises(ValidationError):
        Settings(intent_planner_explore_threshold=threshold)


def test_lookups_discover_live_objects_once_after_snapshot_creation(db: Database) -> None:
    """A stale prompt snapshot cannot prevent live discovery; repeated lookups deduplicate."""
    catalog = build_catalog(db)
    users(db)
    lookups = Lookups(db, catalog, ToolCallContext(actor="local"))
    for _ in range(2):
        assert "person-061" in lookups.found(
            {"look": "objects", "kind": "user", "words": "Person 061"}
        )
    assert [(entry.kind, entry.id) for entry in lookups.discovered] == [("user", "person-061")]


@pytest.mark.parametrize("auto_threshold", [1, 5000])
def test_auto_explore_merges_discovered_user_through_repairs_and_resolution(
    db: Database, auto_threshold: int
) -> None:
    """A person outside the first sixty resolves into a grounded executable action plan."""
    _, south, tasks = two_projects(db)
    users(db)
    assert build_catalog(db).get("user", "person-061") is None
    replies = [
        look("look_objects", kind="user", words="Person 061"),
        ModelResponse(content="not JSON"),
        final(
            steps(
                ("assign_tasks", {"task_ids": tasks[4:6], "actor": "Person 061", "unknown": True})
            )
        ),
        final(steps(("assign_tasks", {"task_ids": tasks[4:6], "actor": "Person 061"}))),
    ]
    sent: list[ModelRequest] = []

    def complete(request: ModelRequest) -> ModelResponse:
        sent.append(request)
        return replies[min(len(sent), len(replies)) - 1]

    turn = PlannerTurn(
        text="Give the two unclaimed tasks to Person 061",
        actor="boss",
        context=PageContext(project_id=south.id),
    )
    result = plan_turn(
        db,
        turn,
        complete=complete,
        access=ModelAccess(
            model="m", allowed=True, explore_mode="auto", explore_threshold=auto_threshold
        ),
    )
    assert sent[0].tools
    assert len(sent) == len(replies)
    assert result is not None
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["actor"] == "person-061"
    assert "Person 061" in result.text + str(result.chain.steps[0].details)


class _LiveProvider:
    """Use a scripted transport through the production provider protocol."""

    def __init__(self) -> None:
        self.scripted = PlannerProvider()

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Record production requests without inheriting the fake-provider mode switch."""
        return self.scripted.complete(request)


@pytest.mark.parametrize(
    ("mode", "fake", "expected"), [("auto", True, False), ("on", True, True), ("auto", False, True)]
)
def test_production_wiring_explores_real_providers_but_keeps_fake_auto_deterministic(
    db: Database, monkeypatch: pytest.MonkeyPatch, mode: str, *, fake: bool, expected: bool
) -> None:
    """Production settings reach the planner while existing fake scripts stay opt-in."""
    monkeypatch.setenv("DATAKEEL_INTENT_PLANNER_EXPLORE", mode)
    monkeypatch.setenv("DATAKEEL_INTENT_PLANNER_EXPLORE_THRESHOLD", "1")
    provider = PlannerProvider() if fake else _LiveProvider()
    conversation = create_conversation(db, ConversationCreate())
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content=REQUEST, context=PageContext()),
            provider=provider,
        )
    )
    requests = (
        provider.requests if isinstance(provider, PlannerProvider) else provider.scripted.requests
    )
    assert bool(requests[0].tools) is expected
    assert any(event.intent is not None and event.intent.kind == "plan" for event in events)
