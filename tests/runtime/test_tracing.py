# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Hostile tracing configuration cannot send golden data off the local machine."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

import pytest
from langsmith import configure
from langsmith.utils import tracing_is_enabled

from datakeel.harness.evaluation import run_evaluation
from datakeel.runtime.tracing import tracing_disabled

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_tracing_when_environment_and_ambient_context_enable_it_force_disable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The installed SDK disable API takes precedence over ambient opt-in switches."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    configure(enabled=True)
    with tracing_disabled():
        assert tracing_is_enabled() is False
    assert tracing_is_enabled() is False


def test_tracing_when_hostile_environment_runs_all_golden_without_external_socket(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard DNS and socket calls across legacy and advanced golden conversations."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "synthetic-tracing-fixture")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://trace-fixture.invalid")
    attempts: list[str] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_resolve = socket.getaddrinfo

    def local(host: object) -> None:
        value = host.decode() if isinstance(host, bytes) else str(host)
        if value not in {"None", "localhost", "127.0.0.1", "::1"} and not value.startswith("/"):
            attempts.append(value)
            pytest.fail("Unexpected external socket connection")

    def connect(connection: socket.socket, address: tuple[str, int] | str) -> None:
        local(address[0] if isinstance(address, tuple) else address)
        original_connect(connection, address)

    def connect_ex(connection: socket.socket, address: tuple[str, int] | str) -> int:
        local(address[0] if isinstance(address, tuple) else address)
        return original_connect_ex(connection, address)

    def resolve(
        host: str | bytes | None, port: str | int | None, *args: object, **kwargs: object
    ) -> list[tuple[object, ...]]:
        local(host)
        return original_resolve(host, port, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    configure(enabled=True)
    report = run_evaluation(db)
    assert report.total == report.passed == 45, [(case.id, case.failures) for case in report.cases]
    assert attempts == []
