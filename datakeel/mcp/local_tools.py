# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose governed memory operations and catalog discovery with durable MCP audit spans."""

from collections.abc import Sequence
from time import perf_counter

from pydantic import Field, ValidationError

from datakeel.actions.policy import digest
from datakeel.core.agent_models import ToolCall, ToolDefinition
from datakeel.core.errors import DatakeelError, NotFoundError
from datakeel.core.memory_models import MemoryUpdate, MemoryWrite
from datakeel.core.models import BoundaryModel, JsonDocument, utcnow
from datakeel.memory.service import list_memories, update_memory
from datakeel.memory.tools import invoke_memory
from datakeel.ontology.tool_models import ToolCallContext, ToolInvocationStart, ToolOutcome
from datakeel.ontology.tool_search import ToolSearchParams, search_tools
from datakeel.storage.database import Database
from datakeel.storage.tool_invocations import begin_invocation, finish_invocation

READ_ONLY_LOCAL_TOOLS = frozenset({"tool_search", "search_memories"})
LOCAL_TOOL_NAMES = frozenset({"tool_search", "search_memories", "write_memory", "update_memory"})


class McpMemorySearchParams(BoundaryModel):
    """Bound memory retrieval by query, dataset scope and result count."""

    query: str | None = Field(default=None, max_length=2000)
    dataset_id: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class McpMemoryUpdateParams(BoundaryModel):
    """Replace memory content without accepting scope or provenance changes."""

    memory_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=6000)


def local_tool_definitions() -> list[ToolDefinition]:
    """Publish full frozen input schemas for discovery and explicit memory operations."""
    definitions = (
        (
            "tool_search",
            "Discover ranked tools in English or Chinese; 搜索工具。",
            ToolSearchParams,
        ),
        (
            "search_memories",
            "Search saved memories by query or dataset; 搜索记忆。",
            McpMemorySearchParams,
        ),
        ("write_memory", "Save explicit memory with PII redaction; 保存记忆。", MemoryWrite),
        (
            "update_memory",
            "Update memory content with PII redaction, preserving scope; 更新记忆。",
            McpMemoryUpdateParams,
        ),
    )
    return [
        ToolDefinition(
            name=name,
            description=description,
            parameters=JsonDocument.model_validate(model.model_json_schema()),
        )
        for name, description, model in definitions
    ]


def _search_memories(
    db: Database, arguments: JsonDocument, context: ToolCallContext
) -> JsonDocument:
    params = McpMemorySearchParams.model_validate(arguments.root)
    entries = list_memories(
        db, dataset_id=params.dataset_id, query=params.query, actor=context.actor
    )[: params.limit]
    return JsonDocument.model_validate(
        {"count": len(entries), "memories": [entry.model_dump(mode="json") for entry in entries]}
    )


def _update_memory(db: Database, arguments: JsonDocument, context: ToolCallContext) -> JsonDocument:
    params = McpMemoryUpdateParams.model_validate(arguments.root)
    # MemoryEntry has no persisted update timestamp; report this operation's business clock.
    updated_at = utcnow()
    entry = update_memory(
        db,
        params.memory_id,
        MemoryUpdate(content=params.content),
        actor=context.actor,
        clock=lambda: updated_at,
    )
    return JsonDocument.model_validate(
        {
            "memory_id": entry.id,
            "dataset_id": entry.dataset_id,
            "content": entry.content,
            "updated_at": updated_at.isoformat(),
        }
    )


def _invoke(
    db: Database,
    name: str,
    arguments: JsonDocument,
    context: ToolCallContext,
    catalog: Sequence[ToolDefinition],
) -> ToolOutcome:
    if name == "write_memory":
        # A transport session is not a persisted conversation; attribution stays in the audit.
        return invoke_memory(
            db,
            ToolCall(name=name, arguments=arguments),
            context.model_copy(update={"session_id": None}),
        )
    if name == "tool_search":
        content = search_tools(catalog, ToolSearchParams.model_validate(arguments.root))
    elif name == "search_memories":
        content = _search_memories(db, arguments, context)
    elif name == "update_memory":
        content = _update_memory(db, arguments, context)
    else:
        msg = f"Unknown local tool: {name}"
        raise NotFoundError(msg)
    return ToolOutcome(name=name, status="SUCCEEDED", content=content)


def invoke_local_tool(
    db: Database,
    name: str,
    arguments: JsonDocument,
    context: ToolCallContext,
    catalog: Sequence[ToolDefinition],
) -> ToolOutcome:
    """Audit every local attempt, including input errors and unexpected dispatch failures."""
    started = perf_counter()
    identifier = begin_invocation(
        db,
        ToolInvocationStart(
            name=name,
            arguments_digest=digest(arguments.root),
            argument_keys=sorted(arguments.root),
            context=context,
            asset_refs=[],
        ),
    )
    try:
        outcome = _invoke(db, name, arguments, context, catalog)
    except (DatakeelError, ValidationError) as error:
        outcome = ToolOutcome(name=name, status="FAILED", error=str(error))
    except Exception as error:
        finish_invocation(
            db,
            ToolOutcome(
                name=name,
                status="FAILED",
                error=f"{type(error).__name__}: {error}",
                invocation_id=identifier,
            ),
            (perf_counter() - started) * 1000,
        )
        raise
    result = outcome.model_copy(update={"invocation_id": identifier})
    finish_invocation(db, result, (perf_counter() - started) * 1000)
    return result
