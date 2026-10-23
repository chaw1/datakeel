# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""CLI transport selection keeps protocol stdout clean and closes database resources."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from datakeel import cli
from datakeel.cli.mcp import serve

if TYPE_CHECKING:
    from typing import Literal

    from datakeel.storage.database import Database
    from tests.cli.conftest import Invoke


def test_mcp_command_when_defaulted_selects_stdio_without_http_arguments(
    invoke: Invoke,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use stdio by default for Desktop and editor subprocess configurations."""
    launched = MagicMock()
    monkeypatch.setattr(cli, "serve", launched)
    invoke("mcp")
    assert launched.call_args.args[1:] == ("stdio", "127.0.0.1", 8766)


@pytest.mark.parametrize("transport", ["stdio", "sse"])
def test_mcp_transport_when_started_disables_banner_and_releases_database(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
    transport: Literal["stdio", "sse"],
) -> None:
    """Reserve stdout for JSON-RPC and clean up after either transport returns."""
    server = MagicMock()
    dispose = MagicMock(wraps=db.engine.dispose)
    monkeypatch.setattr("datakeel.mcp.create_server", lambda _db: server)
    monkeypatch.setattr(db.engine, "dispose", dispose)
    serve(db, transport, "127.0.0.1", 8766)
    assert server.run.call_args.kwargs["show_banner"] is False
    assert server.run.call_args.kwargs["transport"] == transport
    assert ("path" in server.run.call_args.kwargs) == (transport == "sse")
    dispose.assert_called_once()


def test_mcp_transport_when_initialization_fails_still_releases_database(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Close infrastructure even when the server cannot finish constructing tools."""
    dispose = MagicMock(wraps=db.engine.dispose)
    monkeypatch.setattr(
        "datakeel.mcp.create_server", MagicMock(side_effect=RuntimeError("fixture"))
    )
    monkeypatch.setattr(db.engine, "dispose", dispose)
    with pytest.raises(RuntimeError, match="fixture"):
        serve(db, "stdio", "127.0.0.1", 8766)
    dispose.assert_called_once()
