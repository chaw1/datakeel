# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Plan guarded read prefixes and own their bounded worker lifetime."""

from collections import Counter
from collections.abc import Callable, Generator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import Protocol, Self

from datakeel.actions.policy import digest
from datakeel.core.agent_models import ToolCall
from datakeel.core.models import BoundaryModel
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.tool_models import ToolOutcome

PARALLEL_READ_TOOLS: frozenset[str] = frozenset(PARAMETER_MODELS) - {"ask_data"}
MAX_CONCURRENT_READS = 4
_MIN_CONCURRENT_READS = 2


class GuardState(Protocol):
    """Expose only primitive guard state to the lower-layer batch planner."""

    calls: Counter[str]
    failures: Counter[str]
    history: list[str]
    last_result: str | None
    no_progress: int


class ParallelPlanInput(BoundaryModel):
    """Snapshot guard counters and visible capabilities without sharing mutable guard state."""

    calls_count: dict[str, int]
    failures: dict[str, int]
    history: list[str]
    last_result: str | None
    no_progress: int
    repeat_limit: int
    ping_window: int
    allowed_tools: list[str] | None
    visible_tools: set[str]

    @classmethod
    def from_guard(
        cls,
        guard: GuardState,
        repeat_limit: int,
        ping_window: int,
        allowed_tools: list[str] | None,
        visible_tools: set[str],
    ) -> Self:
        """Copy a structural guard view without importing its application implementation."""
        return cls(
            calls_count=dict(guard.calls),
            failures=dict(guard.failures),
            history=guard.history,
            last_result=guard.last_result,
            no_progress=guard.no_progress,
            repeat_limit=repeat_limit,
            ping_window=ping_window,
            allowed_tools=allowed_tools,
            visible_tools=visible_tools,
        )


def can_parallelize(*, sqlite: bool, database: str | None) -> bool:
    """Avoid concurrent transactions sharing an in-memory SQLite connection."""
    return not (sqlite and (not database or database == ":memory:"))


def _eligible(call: ToolCall, state: ParallelPlanInput) -> bool:
    return (
        call.name in PARALLEL_READ_TOOLS
        and call.name in state.visible_tools
        and (state.allowed_tools is None or call.name in state.allowed_tools)
    )


def _observe_call(
    call: ToolCall, counts: Counter[str], history: list[str], state: ParallelPlanInput
) -> bool:
    signature = digest({"name": call.name, "arguments": call.arguments.root})
    counts[signature] += 1
    history.append(signature)
    recent = history[-state.ping_window :]
    return counts[signature] >= state.repeat_limit or (
        len(recent) == state.ping_window and recent[:2] == recent[2:] and recent[0] != recent[1]
    )


def plan_parallel_prefix(calls: Sequence[ToolCall], state: ParallelPlanInput) -> list[ToolCall]:
    """Select only a contiguous prefix that no possible guard outcome can stop early."""
    prefix: list[ToolCall] = []
    counts, names = Counter(state.calls_count), Counter[str]()
    history, identifiers, signatures = list(state.history), set[str](), set[tuple[str, str]]()
    headroom = (
        MAX_CONCURRENT_READS
        if state.last_result is None
        else max(1, state.repeat_limit - state.no_progress)
    )
    for call in calls[: min(MAX_CONCURRENT_READS, headroom)]:
        signature = (call.name, digest(call.arguments.root))
        if not _eligible(call, state) or call.id in identifiers or signature in signatures:
            break
        if _observe_call(call, counts, history, state):
            break
        names[call.name] += 1
        failure_count = state.failures.get(call.name, 0) + names[call.name]
        if failure_count > state.repeat_limit:
            break
        prefix.append(call)
        identifiers.add(call.id)
        signatures.add(signature)
        if failure_count == state.repeat_limit:
            break
    return prefix if len(prefix) >= _MIN_CONCURRENT_READS else []


@contextmanager
def parallel_read_futures(
    calls: Sequence[ToolCall], runner: Callable[[ToolCall], ToolOutcome]
) -> Generator[dict[str, Future[ToolOutcome]]]:
    """Yield submitted reads immediately and join every worker before leaving the turn."""
    if len(calls) < _MIN_CONCURRENT_READS:
        yield {}
        return
    executor = ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_READS, len(calls)))
    try:
        yield {call.id: executor.submit(runner, call) for call in calls}
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
