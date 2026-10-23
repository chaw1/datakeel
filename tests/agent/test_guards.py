# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Each progress detector remains independent of provider wording or action keywords."""

from datakeel.agent.guards import LoopGuard
from datakeel.core.agent_models import ToolCall
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.tool_models import ToolOutcome


def test_repeat_guard_when_third_identical_call_arrives_stops_before_dispatch() -> None:
    """Canonical argument ordering cannot evade the identical-call counter."""
    guard = LoopGuard()
    calls = [
        ToolCall(name="search_files", arguments=JsonDocument(value))
        for value in [{"a": 1, "b": 2}, {"b": 2, "a": 1}, {"a": 1, "b": 2}]
    ]
    assert [guard.observe_call(call) for call in calls] == [None, None, "repeated_call"]


def test_ping_pong_guard_when_second_alternation_completes_stops() -> None:
    """Detect A/B/A/B even though neither call reached the repetition limit."""
    guard = LoopGuard()
    assert [guard.observe_call(ToolCall(name=name)) for name in ["a", "b", "a", "b"]] == [
        None,
        None,
        None,
        "ping_pong",
    ]


def test_failure_guard_when_one_tool_fails_three_times_stops() -> None:
    """Accumulate failures by tool even when arguments and error text change."""
    guard = LoopGuard()
    outcomes = [
        ToolOutcome(name="bad", status="FAILED", content=JsonDocument({"attempt": attempt}))
        for attempt in range(3)
    ]
    assert [guard.observe_outcome(value) for value in outcomes] == [None, None, "tool_failures"]


def test_progress_guard_when_no_new_assets_and_same_result_persists_stops() -> None:
    """Count three unchanged rounds after the initial observation establishes evidence."""
    guard = LoopGuard()
    outcome = ToolOutcome(name="read", status="SUCCEEDED", content=JsonDocument({"count": 1}))
    assert [guard.observe_outcome(outcome) for _ in range(4)] == [None, None, None, "no_progress"]
    fresh = outcome.model_copy(update={"asset_refs": [AssetRef(asset_id="new")]})
    assert guard.observe_outcome(fresh) is None
    assert guard.no_progress == 0


def test_empty_guard_when_three_empty_rounds_occur_stops() -> None:
    """Do not treat an empty completion as a successful final answer."""
    guard = LoopGuard()
    assert [guard.observe_empty() for _ in range(3)] == [None, None, "no_progress"]
