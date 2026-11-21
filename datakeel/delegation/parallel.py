# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Plan safe specialist prefixes and own their bounded concurrent execution."""

from collections import Counter
from collections.abc import Callable, Generator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager

from datakeel.actions.policy import digest
from datakeel.core.agent_models import Conversation, ToolCall
from datakeel.core.errors import DatakeelError
from datakeel.core.models import BoundaryModel
from datakeel.core.settings import get_settings
from datakeel.delegation.loader import get_agent, is_read_only_agent
from datakeel.delegation.models import DelegateParams, DelegationResult
from datakeel.delegation.policy import rejection

_MAX_PARALLEL = 4
_MIN_PARALLEL = 2


class ParallelDelegationInput(BoundaryModel):
    """Freeze parent policy and copy progress counters before starting child threads."""

    parent: Conversation
    start_ordinal: int = 0
    parallel_safe: bool
    sqlite: bool
    database: str | None
    delegate_visible: bool
    calls_count: dict[str, int]
    failures: dict[str, int]
    history: list[str]
    last_result: str | None
    no_progress: int
    repeat_limit: int
    ping_window: int


def _eligible(
    call: ToolCall, state: ParallelDelegationInput, ordinal: int
) -> DelegateParams | None:
    if call.name != "delegate_agent":
        return None
    try:
        params = DelegateParams.model_validate(call.arguments.root)
        definition = get_agent(params.agent)
    except (DatakeelError, ValueError):
        return None
    return (
        params
        if is_read_only_agent(definition) and not rejection(state.parent, definition, ordinal)
        else None
    )


def _observe_call(
    call: ToolCall, counts: Counter[str], history: list[str], state: ParallelDelegationInput
) -> bool:
    signature = digest({"name": call.name, "arguments": call.arguments.root})
    counts[signature] += 1
    history.append(signature)
    recent = history[-state.ping_window :]
    return counts[signature] >= state.repeat_limit or (
        len(recent) == state.ping_window and recent[:2] == recent[2:] and recent[0] != recent[1]
    )


def plan_parallel_delegations(
    calls: Sequence[ToolCall], state: ParallelDelegationInput
) -> list[tuple[ToolCall, int]]:
    """Select a contiguous read-only prefix that preserves serial policy and guard stops."""
    if (
        not state.parallel_safe
        or not state.delegate_visible
        or (state.sqlite and (not state.database or state.database == ":memory:"))
    ):
        return []
    batch: list[tuple[ToolCall, int]] = []
    counts, history = Counter(state.calls_count), list(state.history)
    identifiers, signatures, names = set[str](), set[str](), set[str]()
    headroom = (
        _MAX_PARALLEL
        if state.last_result is None
        else max(1, state.repeat_limit - state.no_progress)
    )
    limit = min(get_settings().delegation_max_parallel, _MAX_PARALLEL, headroom)
    for call in calls[:limit]:
        ordinal = state.start_ordinal + len(batch) + 1
        if (params := _eligible(call, state, ordinal)) is None:
            break
        signature = digest({"agent": params.agent, "task": params.task})
        if call.id in identifiers or signature in signatures or params.agent in names:
            break
        if _observe_call(call, counts, history, state):
            break
        failure_count = state.failures.get("delegate_agent", 0) + len(batch) + 1
        if failure_count > state.repeat_limit:
            break
        batch.append((call, ordinal))
        identifiers.add(call.id)
        signatures.add(signature)
        names.add(params.agent)
        if failure_count == state.repeat_limit:
            break
    return batch if len(batch) >= _MIN_PARALLEL else []


@contextmanager
def parallel_delegation_futures(
    batch: Sequence[tuple[ToolCall, int]], runner: Callable[[ToolCall, int], DelegationResult]
) -> Generator[dict[str, Future[DelegationResult]]]:
    """Yield submitted children immediately and join workers on every exit path."""
    if len(batch) < _MIN_PARALLEL:
        yield {}
        return
    executor = ThreadPoolExecutor(max_workers=len(batch))
    try:
        yield {call.id: executor.submit(runner, call, ordinal) for call, ordinal in batch}
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
