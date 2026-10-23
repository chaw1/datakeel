# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Register schema-derived tools and audit unknown calls before protocol rejection."""

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_context
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import Tool, ToolResult
from mcp_types import CallToolRequestParams, ToolAnnotations
from pydantic import JsonValue, PrivateAttr

from datakeel.core.agent_models import ToolDefinition
from datakeel.core.models import JsonDocument
from datakeel.mcp.catalog import tool_definitions
from datakeel.mcp.dispatch import dispatch
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.database import Database


class ControlledTool(Tool):
    """Keep SDK registration mutable; all domain inputs and outputs remain frozen models."""

    _database: Database = PrivateAttr()

    @classmethod
    def create(cls, db: Database, definition: ToolDefinition) -> "ControlledTool":
        """Reuse domain-generated schemas without preempting the audited validation path."""
        read_only = definition.name in PARAMETER_MODELS
        tool = cls(
            name=definition.name,
            description=definition.description,
            parameters=definition.parameters.root,
            output_schema=ToolOutcome.model_json_schema(),
            annotations=ToolAnnotations(
                read_only_hint=read_only,
                destructive_hint=definition.name == "execute_plan",
                idempotent_hint=read_only,
                open_world_hint=False,
            ),
        )
        tool._database = db
        return tool

    async def run(self, arguments: dict[str, JsonValue]) -> ToolResult:
        """Convert the SDK's JSON mapping to a typed boundary before invoking the domain."""
        return await dispatch(
            self._database, self.name, JsonDocument.model_validate(arguments), get_context()
        )


class UnknownToolAudit(Middleware):
    """Record undeclared tool attempts instead of losing them in protocol lookup errors."""

    def __init__(self, db: Database, names: frozenset[str]) -> None:
        """Bind this server's allowlist and its authoritative audit database."""
        self.database = db
        self.names = names

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
        )


def create_server(db: Database) -> FastMCP:
    """Create registered controlled tools for either stdio or HTTP SSE transport."""
    definitions = tool_definitions()
    server = FastMCP(
        "Datakeel",
        instructions=(
            "Action tools only prepare frozen plans. Obtain a human decision before "
            "approve_plan, then explicitly call execute_plan; approvals cannot be reused."
        ),
    )
    for definition in definitions:
        server.add_tool(ControlledTool.create(db, definition))
    server.add_middleware(UnknownToolAudit(db, frozenset(item.name for item in definitions)))
    return server
