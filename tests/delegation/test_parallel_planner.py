# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound specialist fan-out before any worker can bypass serial policy or guards."""

from threading import Barrier, Event
from unittest.mock import patch

import pytest

from datakeel.actions.policy import digest
from datakeel.core.agent_models import Conversation, ConversationCreate, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.delegation.loader import get_agent, is_read_only_agent
from datakeel.delegation.models import DelegationResult
from datakeel.delegation.parallel import (
    ParallelDelegationInput,
    parallel_delegation_futures,
    plan_parallel_delegations,
)
from datakeel.ontology.tool_models import ToolOutcome


def _call(agent: str, task: str = "Inspect available evidence") -> ToolCall:
    return ToolCall(name="delegate_agent", arguments=JsonDocument({"agent": agent, "task": task}))


def _calls() -> list[ToolCall]:
    return [_call(name) for name in ("catalog-analyst", "production-ops", "training-auditor")]


def _state(**updates: object) -> ParallelDelegationInput:
    return ParallelDelegationInput(
        parent=Conversation(id="parent", config=ConversationCreate()),
        parallel_safe=True,
        sqlite=True,
        database="generated.db",
        delegate_visible=True,
        calls_count={},
        failures={},
        history=[],
        last_result=None,
        no_progress=0,
        repeat_limit=3,
        ping_window=4,
    ).model_copy(update=updates)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("catalog-analyst", True),
        ("production-ops", True),
        ("training-auditor", True),
        ("kg-standard-analyst", True),
        ("evidence-reviewer", False),
        ("metric-manager", False),
    ],
)
def test_specialist_read_only_classification(name: str, *, expected: bool) -> None:
    """Use the registered tool capabilities rather than a specialist name whitelist."""
    assert is_read_only_agent(get_agent(name)) is expected
    assert not is_read_only_agent(get_agent(name).model_copy(update={"tools": ["ask_data"]}))
    assert is_read_only_agent(
        get_agent(name).model_copy(update={"tools": ["tool_search", "delegate_agent"]})
    )


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"parallel_safe": False}, 0),
        ({"delegate_visible": False}, 0),
        ({"database": None}, 0),
        ({"database": ""}, 0),
        ({"database": ":memory:"}, 0),
        ({"sqlite": False, "database": None}, 3),
        ({"last_result": "previous", "no_progress": 2}, 0),
        ({"last_result": "previous", "no_progress": 1}, 2),
        ({"failures": {"delegate_agent": 1}}, 2),
        ({"failures": {"delegate_agent": 2}}, 0),
        ({"failures": {"delegate_agent": 3}}, 0),
        ({"start_ordinal": 1}, 2),
        ({"start_ordinal": 2}, 0),
    ],
)
def test_planner_honors_provider_storage_and_guard_headroom(
    updates: dict[str, object], expected: int
) -> None:
    """Every preflight gate limits the prefix without mutating its input snapshot."""
    calls, state = _calls(), _state(**updates)
    before = state.model_dump()
    planned = plan_parallel_delegations(calls, state)
    assert planned == [
        (call, state.start_ordinal + index + 1) for index, call in enumerate(calls[:expected])
    ]
    assert state.model_dump() == before


@pytest.mark.parametrize("field", ["depth", "allowed_tools"])
def test_parent_depth_and_scope_block_parallel_children(field: str) -> None:
    """Apply the existing delegation policy before submitting any child."""
    state = _state()
    parent = state.parent.model_copy(update={field: 2 if field == "depth" else ["list_datasets"]})
    assert plan_parallel_delegations(_calls(), state.model_copy(update={"parent": parent})) == []


@pytest.mark.parametrize("maximum", [1, 2, 16])
def test_planner_enforces_configured_limit_and_four_worker_ceiling(
    monkeypatch: pytest.MonkeyPatch, maximum: int
) -> None:
    """Higher configured sibling limits still cannot create more than four workers."""
    monkeypatch.setenv("DATAKEEL_DELEGATION_MAX_PARALLEL", str(maximum))
    calls = [*_calls(), _call("kg-standard-analyst")]
    expected = 0 if maximum == 1 else min(maximum, 4)
    assert len(plan_parallel_delegations(calls, _state(repeat_limit=8))) == expected


@pytest.mark.parametrize(
    "unsafe",
    [
        ToolCall(name="list_datasets"),
        ToolCall(name="delegate_agent"),
        _call("unknown-specialist"),
        _call("evidence-reviewer"),
        _call("metric-manager"),
    ],
)
def test_unsafe_candidate_ends_prefix_without_skipping(unsafe: ToolCall) -> None:
    """Never schedule around an intervening action, malformed call or unrelated read."""
    first, second, third = _calls()
    assert plan_parallel_delegations([first, unsafe, second], _state()) == []
    assert plan_parallel_delegations([first, second, unsafe, third], _state()) == [
        (first, 1),
        (second, 2),
    ]


@pytest.mark.parametrize("duplicate", ["id", "task", "agent"])
def test_duplicate_identity_task_or_specialist_stays_sequential(duplicate: str) -> None:
    """Prevent duplicate invocation work and same-specialist child-path collisions."""
    first, second, third = _calls()
    if duplicate == "id":
        second = second.model_copy(update={"id": first.id})
    else:
        second = _call("catalog-analyst", "Different task") if duplicate == "agent" else first
    assert plan_parallel_delegations([first, second, third], _state()) == []


@pytest.mark.parametrize("pattern", ["repeated", "ping_pong"])
def test_simulated_guard_rejects_the_same_call_as_serial_execution(pattern: str) -> None:
    """Include prior dispatches while leaving the live guard's counters untouched."""
    first, second, _ = _calls()
    a, b = [
        digest({"name": call.name, "arguments": call.arguments.root}) for call in (first, second)
    ]
    state = (
        _state(calls_count={b: 2})
        if pattern == "repeated"
        else _state(history=[a, b], calls_count={a: 1, b: 1})
    )
    assert plan_parallel_delegations([first, second], state) == []


@pytest.mark.parametrize("count", [0, 1])
def test_small_batch_never_creates_executor(count: int) -> None:
    """Sequential fallback neither starts threads nor invokes the delegated runner."""
    batch = [(call, index + 1) for index, call in enumerate(_calls()[:count])]
    with (
        patch("datakeel.delegation.parallel.ThreadPoolExecutor", side_effect=AssertionError),
        parallel_delegation_futures(batch, _result) as futures,
    ):
        assert futures == {}


def _result(call: ToolCall, ordinal: int) -> DelegationResult:
    return DelegationResult(
        summary=str(ordinal), outcome=ToolOutcome(name=call.name, status="SUCCEEDED")
    )


def test_pool_yields_live_futures_and_joins_on_exception() -> None:
    """Both workers rendezvous before the context yields control and always finish on exit."""
    barrier, release, completed = Barrier(2, timeout=3), Event(), Event()
    calls = _calls()[:2]
    summaries: list[str] = []

    def run(call: ToolCall, ordinal: int) -> DelegationResult:
        barrier.wait()
        assert release.wait(3), "The pool joined workers before yielding its futures"
        completed.set()
        result = _result(call, ordinal)
        summaries.append(result.summary)
        return result

    def abort() -> None:
        with parallel_delegation_futures(list(zip(calls, (1, 2), strict=True)), run) as futures:
            assert list(futures) == [call.id for call in calls]
            assert not completed.is_set()
            release.set()
            msg = "stop consuming"
            raise ValueError(msg)

    with pytest.raises(ValueError, match="stop consuming"):
        abort()
    assert completed.is_set()
    assert sorted(summaries) == ["1", "2"]
