# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Translate protocol context and results around the shared audited tool dispatcher."""

from collections.abc import Sequence
from functools import partial

from anyio import to_thread
from fastmcp import Context
from fastmcp.tools import ToolResult

from datakeel.core.agent_models import ToolDefinition
from datakeel.core.models import JsonDocument
from datakeel.mcp.local_tools import LOCAL_TOOL_NAMES, invoke_local_tool
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database


def caller_context(context: Context) -> ToolCallContext:
    """Use protocol attribution while keeping the platform actor fixed to local."""
    request = context.request_context
    if request is None:
        return ToolCallContext(agent_id="mcp")
    client = request.session.client_params
    agent = client.client_info.name if client is not None else context.client_id or "mcp"
    return ToolCallContext(agent_id=agent[:128], session_id=context.session_id[:128])


async def dispatch(
    db: Database,
    name: str,
    arguments: JsonDocument,
    context: Context,
    catalog: Sequence[ToolDefinition],
) -> ToolResult:
    """Audit schema failures and business outcomes through the single domain entry point."""
    if name in LOCAL_TOOL_NAMES:
        outcome = await to_thread.run_sync(
            partial(invoke_local_tool, db, name, arguments, caller_context(context), catalog)
        )
    else:
        outcome = await to_thread.run_sync(
            partial(invoke_tool, db, name, arguments, caller_context(context), entry="mcp")
        )
    return ToolResult(
        content=outcome.model_dump_json(),
        structured_content=outcome.model_dump(mode="json"),
        is_error=outcome.status == "FAILED",
    )
