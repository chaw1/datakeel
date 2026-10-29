# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect complete MCP tool discovery within standard SSE event limits."""

from scripts.mutation_models import Mutation

MCP_PAGINATION_MUTATIONS = (
    Mutation(
        name="mcp-tool-list-pagination",
        path="mcp/server.py",
        before="        list_page_size=32,",
        after="        list_page_size=None,",
        case=(
            "tests/mcp/test_server.py::"
            "test_tool_listing_paginates_complete_schemas_below_sse_event_limit"
        ),
        runner="pytest",
    ),
)
