# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parallel planning preserves sequential stopping rules and bounded worker lifetimes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from itertools import product
from threading import Barrier, Event
from typing import TYPE_CHECKING, override

import pytest
from pydantic import ValidationError

from datakeel.actions.policy import digest
from datakeel.agent.guards import LoopGuard
from datakeel.core.agent_models import ToolCall
from datakeel.core.models import JsonDocument
from datakeel.ontology import tool_batch
from datakeel.ontology.tool_batch import (
    MAX_CONCURRENT_READS,
    PARALLEL_READ_TOOLS,
    ParallelPlanInput,
    can_parallelize,
    parallel_read_futures,
    plan_parallel_prefix,
)
from datakeel.ontology.tool_models import ToolOutcome

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future


def _state() -> ParallelPlanInput:
    return ParallelPlanInput(
        calls_count={},
        failures={},
        history=[],
        last_result=None,
        no_progress=0,
        repeat_limit=3,
        ping_window=4,
        allowed_tools=None,
        visible_tools=set(PARALLEL_READ_TOOLS),
    )


def _calls() -> list[ToolCall]:
    return [
        ToolCall(id=str(index), name=name)
        for index, name in enumerate(
            ["list_datasets", "search_files", "get_quality", "get_lineage", "get_report"]
        )
    ]


def _signature(call: ToolCall) -> str:
    return digest({"name": call.name, "arguments": call.arguments.root})


@pytest.mark.parametrize(
    ("sqlite", "database", "expected"),
    [
        (True, None, False),
        (True, "", False),
        (True, ":memory:", False),
        (True, "local.db", True),
        (False, None, True),
        (False, "fixture", True),
    ],
)
def test_database_connection_safety(database: str | None, *, sqlite: bool, expected: bool) -> None:
    """Only SQLite without an independent file connection declines concurrency."""
    assert can_parallelize(sqlite=sqlite, database=database) is expected


@pytest.mark.parametrize(
    "name", ["ask_data", "tool_search", "write_memory", "delegate_agent", "quarantine_files"]
)
def test_stateful_tools_end_the_eligible_prefix(name: str) -> None:
    """Discovery, questions, delegation, memory and actions remain sequential barriers."""
    calls = _calls()
    blocked = ToolCall(name=name)
    state = _state().model_copy(update={"visible_tools": {*PARALLEL_READ_TOOLS, name}})
    assert name not in PARALLEL_READ_TOOLS
    assert plan_parallel_prefix([blocked, *calls], state) == []
    assert plan_parallel_prefix([*calls[:2], blocked, *calls[2:]], state) == calls[:2]


@pytest.mark.parametrize("restricted", ["visible_tools", "allowed_tools"])
def test_hidden_or_disallowed_tools_never_start(restricted: str) -> None:
    """A valid read still needs discovery and delegated scope before speculative execution."""
    calls = _calls()
    state = _state().model_copy(update={restricted: [calls[0].name]})
    assert plan_parallel_prefix(calls, state) == []


@pytest.mark.parametrize("duplicate", ["id", "arguments"])
def test_duplicate_ids_or_canonical_arguments_stay_sequential(duplicate: str) -> None:
    """Distinct requests need unique invocation identities and canonical argument signatures."""
    first = ToolCall(id="first", name="list_datasets", arguments=JsonDocument({"a": 1, "b": 2}))
    second = (
        ToolCall(id="first", name="get_quality")
        if duplicate == "id"
        else ToolCall(id="second", name=first.name, arguments=JsonDocument({"b": 2, "a": 1}))
    )
    assert plan_parallel_prefix([first, second], _state()) == []


@pytest.mark.parametrize("position", [0, 1, 2])
def test_repeated_call_guard_is_simulated_before_accepting(position: int) -> None:
    """A call that would be refused cannot launch in a worker."""
    calls = _calls()
    state = _state().model_copy(update={"calls_count": {_signature(calls[position]): 2}})
    assert plan_parallel_prefix(calls, state) == (calls[:position] if position >= 2 else [])


def test_ping_pong_and_state_immutability() -> None:
    """Planning detects a second alternating cycle without changing the supplied snapshot."""
    calls = _calls()
    signatures = [_signature(call) for call in calls[:2]]
    state = _state().model_copy(
        update={"history": signatures, "calls_count": dict.fromkeys(signatures, 1)}
    )
    before = state.model_dump()
    assert plan_parallel_prefix(calls, state) == []
    assert state.model_dump() == before
    with pytest.raises(ValidationError, match="frozen"):
        state.no_progress = 1


def test_guard_adapter_copies_live_counters_and_history() -> None:
    """Planning a snapshot cannot mutate the running guard's collections."""
    guard, calls = LoopGuard(), _calls()
    assert guard.observe_call(calls[0]) is None
    state = ParallelPlanInput.from_guard(guard, 3, 4, None, set(PARALLEL_READ_TOOLS))
    assert state.calls_count == dict(guard.calls)
    assert state.history == guard.history
    state.history.clear()
    state.calls_count.clear()
    assert guard.history == [_signature(calls[0])]
    assert guard.calls[_signature(calls[0])] == 1


@pytest.mark.parametrize("failures", [2, 3])
def test_possible_first_failure_stop_prevents_following_different_tool(failures: int) -> None:
    """Per-name headroom cannot speculate past an earlier tool's possible terminal failure."""
    calls = _calls()
    state = _state().model_copy(update={"failures": {calls[0].name: failures}})
    assert plan_parallel_prefix(calls, state) == []


def test_failure_threshold_is_allowed_only_at_end_of_batch() -> None:
    """The final read may stop the turn; a later different tool must wait for its outcome."""
    calls = [
        ToolCall(name="list_datasets", arguments=JsonDocument({"limit": limit})) for limit in (1, 2)
    ]
    state = _state().model_copy(update={"failures": {"list_datasets": 1}})
    assert plan_parallel_prefix([*calls, ToolCall(name="get_quality")], state) == calls


@pytest.mark.parametrize(
    ("last_result", "no_progress", "length"),
    [(None, 0, 4), (None, 2, 4), ("seen", 0, 3), ("seen", 1, 2), ("seen", 2, 0), ("seen", 3, 0)],
)
def test_stagnant_result_headroom(last_result: str | None, no_progress: int, length: int) -> None:
    """Even identical outcomes cannot stop before the last launched read."""
    calls = _calls()
    state = _state().model_copy(update={"last_result": last_result, "no_progress": no_progress})
    assert plan_parallel_prefix(calls, state) == calls[:length]
    assert length <= MAX_CONCURRENT_READS


@pytest.mark.parametrize("prior_failures", [0, 1, 2])
@pytest.mark.parametrize("stagnation", [None, 0, 1, 2])
def test_every_failure_combination_keeps_real_guard_stop_at_batch_end(
    prior_failures: int, stagnation: int | None
) -> None:
    """Exhaust outcomes against the actual guard, including cross-name failure stops."""
    calls = _calls()
    fingerprint = digest({}) if stagnation is not None else None
    state = _state().model_copy(
        update={
            "failures": {"search_files": prior_failures},
            "last_result": fingerprint,
            "no_progress": stagnation or 0,
        }
    )
    batch = plan_parallel_prefix(calls, state)
    for failed in product((False, True), repeat=len(batch)):
        guard = LoopGuard()
        guard.failures.update(state.failures)
        guard.last_result, guard.no_progress = fingerprint, stagnation or 0
        for index, (call, failure) in enumerate(zip(batch, failed, strict=True)):
            assert guard.observe_call(call) is None
            reason = guard.observe_outcome(
                ToolOutcome(name=call.name, status="FAILED" if failure else "SUCCEEDED")
            )
            assert reason is None or index == len(batch) - 1


@pytest.mark.parametrize("count", [0, 1])
def test_short_batches_do_not_create_executor(count: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sequential fallback does not pay for or launch a worker pool."""

    def forbidden(*, max_workers: int) -> None:
        pytest.fail("A short batch must not create an executor")

    monkeypatch.setattr(tool_batch, "ThreadPoolExecutor", forbidden)
    with parallel_read_futures(
        _calls()[:count], lambda call: ToolOutcome(name=call.name, status="SUCCEEDED")
    ) as futures:
        assert futures == {}


def test_futures_are_yielded_before_slow_worker_returns() -> None:
    """Two active workers synchronize, while the first result remains independently readable."""
    calls, barrier, release = _calls()[:2], Barrier(2, timeout=3), Event()

    def runner(call: ToolCall) -> ToolOutcome:
        barrier.wait()
        if call == calls[1]:
            assert release.wait(3)
        return ToolOutcome(name=call.name, status="SUCCEEDED")

    with parallel_read_futures(calls, runner) as futures:
        try:
            assert list(futures) == [call.id for call in calls]
            assert futures[calls[0].id].result(timeout=3).name == calls[0].name
            assert not futures[calls[1].id].done()
        finally:
            release.set()
    assert all(future.done() for future in futures.values())


@pytest.mark.parametrize("failure", ["runner", "consumer", "submit"])
def test_executor_is_joined_and_pending_futures_cancelled_on_error(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every exceptional exit shuts down the acquired executor before control escapes."""
    shutdowns: list[tuple[bool, bool]] = []

    class Executor(ThreadPoolExecutor):
        def submit(
            self, fn: Callable[[ToolCall], ToolOutcome], call: ToolCall
        ) -> Future[ToolOutcome]:
            if failure == "submit":
                msg = "submit failed"
                raise RuntimeError(msg)
            return super().submit(fn, call)

        @override
        def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
            shutdowns.append((wait, cancel_futures))
            super().shutdown(wait=wait, cancel_futures=cancel_futures)

    def runner(call: ToolCall) -> ToolOutcome:
        if failure == "runner":
            msg = "runner failed"
            raise RuntimeError(msg)
        return ToolOutcome(name=call.name, status="SUCCEEDED")

    def consume() -> None:
        with parallel_read_futures(_calls()[:2], runner) as futures:
            if failure == "consumer":
                msg = "consumer failed"
                raise RuntimeError(msg)
            next(iter(futures.values())).result(timeout=3)

    monkeypatch.setattr(tool_batch, "ThreadPoolExecutor", Executor)
    with pytest.raises(RuntimeError, match="failed"):
        consume()
    assert shutdowns == [(True, True)]
