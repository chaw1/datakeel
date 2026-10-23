# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Four independent bounded-progress checks for unproductive model tool loops."""

from collections import Counter

from datakeel.actions.policy import digest
from datakeel.core.agent_models import ToolCall
from datakeel.core.models import BoundaryModel
from datakeel.ontology.tool_models import ToolOutcome

REPEAT_LIMIT = 3
PING_WINDOW = 4


class GuardSnapshot(BoundaryModel):
    """Encode progress counters as basic values without serializing a live guard object."""

    calls: dict[str, int]
    failures: dict[str, int]
    history: list[str]
    last_result: str | None
    no_progress: int
    seen_assets: list[tuple[str, str, str | None]]


class LoopGuard:
    """Track repeated requests, alternating requests, failures, and unchanged evidence."""

    def __init__(self) -> None:
        """Begin one response with independent counters for each failure mode."""
        self.calls: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()
        self.history: list[str] = []
        self.last_result: str | None = None
        self.no_progress = 0
        self.seen_assets: set[tuple[str, str, str | None]] = set()

    def observe_call(self, call: ToolCall) -> str | None:
        """Stop before the third identical dispatch or a second A/B cycle."""
        signature = digest({"name": call.name, "arguments": call.arguments.root})
        self.calls[signature] += 1
        self.history.append(signature)
        if self.calls[signature] >= REPEAT_LIMIT:
            return "repeated_call"
        recent = self.history[-PING_WINDOW:]
        if len(recent) == PING_WINDOW and recent[:2] == recent[2:] and recent[0] != recent[1]:
            return "ping_pong"
        return None

    def observe_outcome(self, outcome: ToolOutcome) -> str | None:
        """Stop after three tool failures or three consecutive stagnant observations.

        连续 3 轮没有新的 asset_ref 进入上下文且工具结果摘要哈希不变, 判为无进展。
        No progress means both that the canonical result-content digest
        equals the preceding result and that no new (asset_type, asset_id, version)
        identity appears in asset_refs. The first observation establishes a baseline.
        Changed result content or any unseen asset resets the counter; empty model
        rounds also increment it through observe_empty. Three stagnant observations
        stop the response, independently of per-tool failure and call-pattern guards.
        """
        if outcome.status == "FAILED":
            self.failures[outcome.name] += 1
            if self.failures[outcome.name] >= REPEAT_LIMIT:
                return "tool_failures"
        fingerprint = digest(outcome.content.root)
        refs = {(ref.asset_type, ref.asset_id, ref.version) for ref in outcome.asset_refs}
        stagnant = not refs.difference(self.seen_assets) and fingerprint == self.last_result
        self.seen_assets.update(refs)
        self.no_progress = self.no_progress + 1 if stagnant else 0
        self.last_result = fingerprint
        return "no_progress" if self.no_progress >= REPEAT_LIMIT else None

    def observe_empty(self) -> str | None:
        """Count empty model rounds as a separate absence of useful progress."""
        self.no_progress += 1
        return "no_progress" if self.no_progress >= REPEAT_LIMIT else None

    def snapshot(self) -> str:
        """Preserve the same counters across synchronous checkpoint boundaries."""
        return GuardSnapshot(
            calls=dict(self.calls),
            failures=dict(self.failures),
            history=self.history,
            last_result=self.last_result,
            no_progress=self.no_progress,
            seen_assets=list(self.seen_assets),
        ).model_dump_json()

    def restore(self, payload: str) -> None:
        """Restore only the explicitly declared basic counter fields."""
        if payload:
            state = GuardSnapshot.model_validate_json(payload)
            self.calls, self.failures = Counter(state.calls), Counter(state.failures)
            self.history, self.last_result = state.history, state.last_result
            self.no_progress, self.seen_assets = state.no_progress, set(state.seen_assets)
