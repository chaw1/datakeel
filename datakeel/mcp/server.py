# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Register schema-derived tools and audit unknown calls before protocol rejection."""

import json

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_context
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import Tool, ToolResult
from mcp_types import CallToolRequestParams, ToolAnnotations
from pydantic import JsonValue, PrivateAttr

from datakeel.core.agent_models import ToolDefinition
from datakeel.core.json_schema import compact_schema
from datakeel.core.models import JsonDocument
from datakeel.delegation.loader import list_agents
from datakeel.mcp.catalog import tool_definitions
from datakeel.mcp.dispatch import dispatch
from datakeel.mcp.local_tools import READ_ONLY_LOCAL_TOOLS
from datakeel.memory.service import list_memories
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.database import Database
from datakeel.versioning import require_current

# Every tool shares this result schema; repeated model titles would push tools/list past the
# 1 MiB server-sent event limit of SSE clients once all feature tools are registered.
OUTPUT_SCHEMA = compact_schema(JsonDocument.model_validate(ToolOutcome.model_json_schema())).root


class ControlledTool(Tool):
    """Keep SDK registration mutable; all domain inputs and outputs remain frozen models."""

    _database: Database = PrivateAttr()
    _catalog: tuple[ToolDefinition, ...] = PrivateAttr()

    @classmethod
    def create(
        cls, db: Database, definition: ToolDefinition, catalog: tuple[ToolDefinition, ...]
    ) -> "ControlledTool":
        """Reuse domain-generated schemas without preempting the audited validation path."""
        read_only = definition.name in PARAMETER_MODELS or definition.name in READ_ONLY_LOCAL_TOOLS
        tool = cls(
            name=definition.name,
            description=definition.description,
            parameters=definition.parameters.root,
            output_schema=OUTPUT_SCHEMA,
            annotations=ToolAnnotations(
                read_only_hint=read_only,
                destructive_hint=False,
                idempotent_hint=read_only,
                open_world_hint=False,
            ),
        )
        tool._database = db
        tool._catalog = catalog
        return tool

    async def run(self, arguments: dict[str, JsonValue]) -> ToolResult:
        """Convert the SDK's JSON mapping to a typed boundary before invoking the domain."""
        return await dispatch(
            self._database,
            self.name,
            JsonDocument.model_validate(arguments),
            get_context(),
            self._catalog,
        )


class UnknownToolAudit(Middleware):
    """Record undeclared tool attempts instead of losing them in protocol lookup errors."""

    def __init__(self, db: Database, catalog: tuple[ToolDefinition, ...]) -> None:
        """Bind this server's allowlist and its authoritative audit database."""
        self.database = db
        self.catalog = catalog
        self.names = frozenset(item.name for item in catalog)

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Delegate registered tools and audit unknown names through the same dispatcher."""
        if context.message.name in self.names:
            return await call_next(context)
        return await dispatch(
            self.database,
            context.message.name,
            JsonDocument.model_validate(context.message.arguments or {}),
            get_context(),
            self.catalog,
        )


def create_server(db: Database) -> FastMCP:
    """Create registered controlled tools for either stdio or HTTP SSE transport."""
    definitions = tuple(tool_definitions())
    if db.sqlite:
        require_current(db)
    server = FastMCP(
        "Datakeel",
        # Keep complete per-tool schemas while bounding each standard tools/list response.
        list_page_size=32,
        instructions=(
            "Action tools only prepare frozen plans. This server has no approve or execute "
            "tool: a person reviews, approves and executes a plan on the Web UI or CLI."
        ),
    )
    for definition in definitions:
        server.add_tool(ControlledTool.create(db, definition, definitions))
    server.add_middleware(UnknownToolAudit(db, definitions))

    @server.resource("datakeel://agents", mime_type="application/json")
    def agents_resource() -> str:
        """List the bundled specialist contracts without running an agent."""
        return json.dumps(
            [agent.model_dump(mode="json") for agent in list_agents()],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @server.resource("datakeel://memories", mime_type="application/json")
    def memories_resource() -> str:
        """Read the current visible memories without changing content or strength."""
        return json.dumps(
            [entry.model_dump(mode="json") for entry in list_memories(db)],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    return server
