# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep legacy reads resident and discover catalog reads and controlled actions on demand."""

from time import perf_counter

from pydantic import Field, ValidationError

from datakeel.actions.policy import digest
from datakeel.actions.registry import action_definitions
from datakeel.agent.schemas import compact_schema
from datakeel.core.agent_models import Conversation, ToolCall, ToolDefinition
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.ontology.functions import function_definitions
from datakeel.ontology.tool_models import ToolCallContext, ToolInvocationStart, ToolOutcome
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database
from datakeel.storage.tool_invocations import begin_invocation, finish_invocation

DEFERRED_READ_FUNCTIONS = frozenset({"ask_data", "list_metrics", "explain_metric", "impact_of"})


class ToolSearchParams(BoundaryModel):
    """Search read tool names or controlled action names and effects."""

    query: str = Field(min_length=1, max_length=200)


def resident_tools() -> list[ToolDefinition]:
    """Preserve the nine original read schemas and the bounded discovery tool."""
    return [
        *[
            ToolDefinition(
                name=item.id,
                description=f"Read {item.id}",
                parameters=compact_schema(item.input_schema),
            )
            for item in function_definitions()
            if item.id not in DEFERRED_READ_FUNCTIONS
        ],
        ToolDefinition(
            name="tool_search",
            description="Discover read tools or controlled actions; actions only prepare.",
            parameters=compact_schema(
                JsonDocument.model_validate(ToolSearchParams.model_json_schema())
            ),
        ),
    ]


def deferred_tools() -> list[ToolDefinition]:
    """Never advertise approval or execution authority to the model."""
    reads = [
        ToolDefinition(
            name=item.id,
            description=f"Read {item.id}",
            parameters=compact_schema(item.input_schema),
        )
        for item in function_definitions()
        if item.id in DEFERRED_READ_FUNCTIONS
    ]
    return [
        *reads,
        *[
            ToolDefinition(
                name=item.id,
                description=f"Prepare {item.id}: {', '.join(item.effects)}",
                parameters=compact_schema(item.params_schema),
            )
            for item in action_definitions()
        ],
    ]


class ToolCatalog:
    """Track discovered schemas within a persisted conversation."""

    def __init__(self, conversation: Conversation) -> None:
        """Recover only discoverable read and action schemas from persisted search results."""
        self.core = resident_tools()
        self.loaded: dict[str, ToolDefinition] = {}
        for message in conversation.messages:
            if message.role == "tool" and message.name == "tool_search":
                result = ToolOutcome.model_validate_json(message.content)
                self._load(result)

    def invoke(self, db: Database, call: ToolCall, context: ToolCallContext) -> ToolOutcome:
        """Enforce model-visible capabilities even if a provider invents a hidden call."""
        if call.name == "tool_search":
            try:
                query = ToolSearchParams.model_validate(call.arguments.root).query.casefold()
                matches = [
                    tool
                    for tool in deferred_tools()
                    if query in f"{tool.name} {tool.description}".casefold()
                ]
                exact = [tool for tool in matches if tool.name.casefold() == query]
                matches = exact or matches
                result = ToolOutcome(
                    name=call.name,
                    status="SUCCEEDED",
                    content=JsonDocument.model_validate(
                        {"tools": [tool.model_dump(mode="json") for tool in matches]}
                    ),
                )
                self._load(result)
            except ValidationError as error:
                result = ToolOutcome(name=call.name, status="FAILED", error=str(error))
            return _record_local(db, call, context, result)
        allowed = {tool.name for tool in self.core} | self.loaded.keys()
        if call.name not in allowed:
            result = ToolOutcome(
                name=call.name,
                status="FAILED",
                error="Tool unavailable; discover allowed tools first",
            )
            return _record_local(db, call, context, result)
        return invoke_tool(db, call.name, call.arguments, context)

    def _load(self, result: ToolOutcome) -> None:
        values = result.content.root.get("tools", [])
        if isinstance(values, list):
            allowed = {tool.name for tool in deferred_tools()}
            for value in values:
                tool = ToolDefinition.model_validate(value)
                if tool.name in allowed:
                    self.loaded[tool.name] = tool


def _record_local(
    db: Database, call: ToolCall, context: ToolCallContext, outcome: ToolOutcome
) -> ToolOutcome:
    started = perf_counter()
    identifier = begin_invocation(
        db,
        ToolInvocationStart(
            name=call.name,
            arguments_digest=digest(call.arguments.root),
            argument_keys=sorted(call.arguments.root),
            context=context,
            asset_refs=[],
        ),
    )
    result = outcome.model_copy(update={"invocation_id": identifier})
    finish_invocation(db, result, (perf_counter() - started) * 1000)
    return result
