# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Observe guard delegation without opening any real network connection."""

import socket

import pytest

from tests.offline_network import guard_external_network


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost", b"localhost"])
def test_loopback_resolution_and_connections_reach_original_functions(
    monkeypatch: pytest.MonkeyPatch, host: str | bytes
) -> None:
    """Local PostgreSQL reaches the actual resolver and both original connect methods."""
    calls: list[object] = []

    def resolve(*args: object, **kwargs: object) -> list[object]:
        calls.append(args[0])
        return []

    def connect(sock: socket.socket, address: object) -> int:
        calls.append(address)
        return 0

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect)
    guard_external_network(monkeypatch)
    assert socket.getaddrinfo(host, 5432) == []
    with socket.socket() as sock:
        sock.connect((host, 5432))
        assert sock.connect_ex((host, 5432)) == 0
    assert calls == [host, (host, 5432), (host, 5432)]


@pytest.mark.parametrize(
    "host", ["192.0.2.1", "2001:db8::1", "api.example.invalid", "localhost.evil"]
)
def test_external_dns_and_connections_fail_before_original_functions(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    """Every rejected destination fails locally, even if a lower transport would succeed."""

    def unexpected(*args: object, **kwargs: object) -> None:
        msg = "External destination reached the original transport"
        raise AssertionError(msg)

    monkeypatch.setattr(socket, "getaddrinfo", unexpected)
    monkeypatch.setattr(socket.socket, "connect", unexpected)
    monkeypatch.setattr(socket.socket, "connect_ex", unexpected)
    guard_external_network(monkeypatch)
    with pytest.raises(pytest.fail.Exception, match="external DNS"):
        socket.getaddrinfo(host, 443)
    with socket.socket() as sock:
        with pytest.raises(pytest.fail.Exception, match="external connection"):
            sock.connect((host, 443))
        with pytest.raises(pytest.fail.Exception, match="external connection"):
            sock.connect_ex((host, 443))
