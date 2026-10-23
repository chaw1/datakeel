# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read child hierarchy and measured calls without exposing hidden session lists."""

from datakeel.delegation.models import CallTree, CallTreeNode
from datakeel.storage.conversation_store import get, list_all
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces
from datakeel.storage.tool_invocations import list_invocations


def call_tree(db: Database, conversation_id: str) -> CallTree:
    """Return a root's complete call tree with deterministic path and trace ordering."""
    root = get(db, conversation_id)
    root_id = root.root_conversation_id or root.id
    traces = list_traces(db, root_id)
    nodes = [
        CallTreeNode(
            id=item.id,
            parent_id=item.parent_conversation_id,
            root_id=root_id,
            agent_name=item.agent_name,
            agent_path=item.agent_path,
            depth=item.depth,
            parent_tool_call_id=item.parent_tool_call_id,
            tokens=sum(
                trace.accounted_tokens for trace in traces if trace.conversation_id == item.id
            ),
            tools=[tool.name for tool in list_invocations(db, item.id)],
        )
        for item in list_all(db, include_children=True)
        if root_id in (item.id, item.root_conversation_id)
    ]
    return CallTree(nodes=sorted(nodes, key=lambda item: item.agent_path), traces=traces)
