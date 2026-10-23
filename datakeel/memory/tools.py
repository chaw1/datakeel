# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One deferred memory-writing capability with durable replay attribution."""

from pydantic import ValidationError

from datakeel.core.agent_models import ToolCall, ToolDefinition
from datakeel.core.errors import DatakeelError
from datakeel.core.memory_models import MemoryCreate, MemoryWrite
from datakeel.core.models import JsonDocument
from datakeel.memory.service import create_memory
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.storage.database import Database
from datakeel.storage.tool_invocations import invocation_identity


def memory_tool() -> ToolDefinition:
    """Declare explicit writing for discovery without making it a resident capability."""
    return ToolDefinition(
        name="write_memory",
        description="Remember explicit information globally or for one dataset; redact PII.",
        parameters=JsonDocument.model_validate(MemoryWrite.model_json_schema()),
    )


def invoke_memory(db: Database, call: ToolCall, context: ToolCallContext) -> ToolOutcome:
    """Write one validated memory without returning its content to historical tool results."""
    try:
        params = MemoryWrite.model_validate(call.arguments.root)
        entry = create_memory(
            db,
            MemoryCreate(
                **params.model_dump(),
                source_conversation_id=context.session_id,
                idempotency_key=invocation_identity(context.session_id, call.id) or call.id,
            ),
        )
        return ToolOutcome(
            name=call.name,
            status="SUCCEEDED",
            content=JsonDocument.model_validate(
                {
                    "memory_id": entry.id,
                    "dataset_id": entry.dataset_id,
                    "source_conversation_ids": entry.source_conversation_ids,
                }
            ),
        )
    except (DatakeelError, ValidationError) as error:
        return ToolOutcome(name=call.name, status="FAILED", error=str(error))
