# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run the local controlled tool server with explicit stdio or legacy SSE transport."""

from typing import Literal

from datakeel.storage.database import Database


def serve(db: Database, transport: Literal["stdio", "sse"], host: str, port: int) -> None:
    """Keep stdout protocol-only and release the database when the transport exits."""
    # Server dependencies are unnecessary for offline demo and evaluation commands.
    from datakeel.mcp import create_server  # noqa: PLC0415

    try:
        server = create_server(db)
        if transport == "stdio":
            server.run(transport="stdio", show_banner=False)
        else:
            server.run(transport="sse", host=host, port=port, path="/sse", show_banner=False)
    finally:
        db.engine.dispose()
