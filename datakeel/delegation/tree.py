# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read child hierarchy and measured calls without exposing hidden session lists."""

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

from datakeel.delegation.models import CallTree, CallTreeNode
from datakeel.storage.conversation_store import get, list_all
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces
from datakeel.storage.tool_invocations import list_invocations_by_sessions

if TYPE_CHECKING:
    from datakeel.core.harness_models import ModelCallTrace


def call_tree(db: Database, conversation_id: str) -> CallTree:
    """Return a root's complete call tree with deterministic path and trace ordering."""
    root = get(db, conversation_id)
    root_id = root.root_conversation_id or root.id
    traces = list_traces(db, root_id)
    family = list_all(db, root_id=root_id)
    invocations = list_invocations_by_sessions(db, [item.id for item in family])
    node_traces: dict[str, list[ModelCallTrace]] = defaultdict(list)
    for trace in traces:
        node_traces[trace.conversation_id].append(trace)
    nodes = [
        CallTreeNode(
            id=item.id,
            parent_id=item.parent_conversation_id,
            root_id=root_id,
            agent_name=item.agent_name,
            agent_path=item.agent_path,
            depth=item.depth,
            parent_tool_call_id=item.parent_tool_call_id,
            tokens=sum(trace.accounted_tokens for trace in node_traces[item.id]),
            tools=[tool.name for tool in invocations[item.id]],
            cost_usd=sum((trace.cost_usd for trace in node_traces[item.id]), Decimal(0)),
            model_calls=len(node_traces[item.id]),
            tool_elapsed_ms=round(sum(tool.elapsed_ms for tool in invocations[item.id]), 2),
            failed_tools=sum(tool.status == "FAILED" for tool in invocations[item.id]),
        )
        for item in family
    ]
    return CallTree(
        nodes=sorted(nodes, key=lambda item: item.agent_path),
        traces=traces,
        total_tokens=sum(trace.accounted_tokens for trace in traces),
        total_cost_usd=sum((trace.cost_usd for trace in traces), Decimal(0)),
        total_tool_calls=sum(len(tools) for tools in invocations.values()),
        total_tool_elapsed_ms=round(
            sum(tool.elapsed_ms for tools in invocations.values() for tool in tools), 2
        ),
        models=list(dict.fromkeys(f"{trace.provider}/{trace.model}" for trace in traces)),
    )
