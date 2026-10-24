# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed golden conversations and persistent evaluation result contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from datakeel.core.agent_models import ConversationCreate, ScriptedResponse
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument


class PlanOperation(BoundaryModel):
    """Simulate a separate human UI decision or an explicit execution attempt."""

    operation: Literal["approve", "reject", "execute", "change_quality_config"]
    canonical_params: JsonDocument | None = None


class GoldenTurn(BoundaryModel):
    """Supply user text, scripted model responses, and subsequent user decisions."""

    input: str
    script: list[ScriptedResponse] = Field(default_factory=list[ScriptedResponse])
    operations: list[PlanOperation] = Field(default_factory=list[PlanOperation])
    new_conversation: bool = False
    delete_memories: bool = False


class ExpectedAction(BoundaryModel):
    """Assert the actual action policy and number of successful executions."""

    action_type: str
    requires_approval: bool
    executions: int = Field(default=0, ge=0)
    selection_from_tool: str | None = None
    output_matches_selection: bool = False


class ExpectedToolResult(BoundaryModel):
    """Validate actual tool content against a declared JSON Schema and source identities."""

    name: str
    status: Literal["SUCCEEDED", "FAILED"] = "SUCCEEDED"
    calls: int = Field(default=1, ge=1)
    call_index: int | None = Field(default=None, ge=0)
    content_schema: JsonDocument
    asset_refs_required: bool = True


class ObservedToolResult(BoundaryModel):
    """Retain real tool responses independently of the scripted assistant's final answer."""

    name: str
    status: Literal["SUCCEEDED", "FAILED"]
    content: JsonDocument
    asset_refs: list[AssetRef]


class GoldenExpect(BoundaryModel):
    """Declare observable assertions, never the result of the scenario itself."""

    tool_sequence: list[str] | None = None
    tool_set: list[str] | None = None
    actions: list[ExpectedAction] = Field(default_factory=list[ExpectedAction])
    tool_results: list[ExpectedToolResult] = Field(default_factory=list[ExpectedToolResult])
    answer_contains: list[str] = Field(default_factory=list[str])
    answer_not_contains: list[str] = Field(default_factory=list[str])
    stop_contains: list[str] = Field(default_factory=list[str])
    context_contains: list[str] = Field(default_factory=list[str])
    context_not_contains: list[str] = Field(default_factory=list[str])
    memory_count: int | None = Field(default=None, ge=0)
    memory_used: bool | None = None
    operation_statuses: list[str] | None = None
    operation_errors: list[str] = Field(default_factory=list[str])
    max_turns: int = Field(default=20, ge=0)
    max_tokens: int = Field(default=100_000, ge=0)
    file_count: int | None = None
    quarantined_count: int | None = None


class GoldenCase(BoundaryModel):
    """Describe a multi-turn deterministic regression against the real runtime."""

    id: str
    description: str
    fixture_kind: Literal["legacy", "evidence", "enterprise", "injection", "kg"] = "legacy"
    config: ConversationCreate = Field(default_factory=ConversationCreate)
    turns: list[GoldenTurn] = Field(min_length=1)
    expect: GoldenExpect


class CaseFixture(BoundaryModel):
    """Bind generated asset identities without supplying expected extraction observations."""

    dataset_id: str
    file_id: str
    unknown_file_id: str = ""
    version_id: str = ""
    relation_id: str = ""


class EvalCaseResult(BoundaryModel):
    """Record measured execution evidence and every failed assertion for one case."""

    id: str
    passed: bool
    failures: list[str]
    tool_sequence: list[str]
    action_types: list[str]
    operations: list[str]
    final_answer: str
    stop_reasons: list[str]
    turns: int
    tokens: int
    cost_usd: Decimal
    tool_results: list[ObservedToolResult] = Field(default_factory=list[ObservedToolResult])
    output_version_files: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    fixture_error: str | None = None


class EvalReport(BoundaryModel):
    """Persist one suite run and explicit deltas from its last comparable run."""

    id: str
    provider: str
    suite_digest: str
    created_at: datetime
    passed: int
    total: int
    cases: list[EvalCaseResult]
    total_tokens: int
    total_cost_usd: Decimal
    previous_id: str | None = None
    previous_suite_digest: str | None = None
    passed_delta: int | None = None
    token_delta: int | None = None
    cost_delta: Decimal | None = None
