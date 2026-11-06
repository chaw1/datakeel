# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Block external sockets while retaining local test databases and Unix sockets."""

import socket
from ipaddress import ip_address

import pytest


def _loopback(host: object) -> bool:
    if host in ("localhost", b"localhost"):
        return True
    try:
        address = ip_address(host.decode("ascii") if isinstance(host, bytes) else str(host))
    except (ValueError, UnicodeError):
        return False
    return address.is_loopback


def guard_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep DNS and both socket connection paths local without disabling database tests."""
    resolve = socket.getaddrinfo
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex

    def local_resolve(host: object, *args: object, **kwargs: object) -> object:
        if not _loopback(host):
            pytest.fail("Offline test attempted external DNS")
        return resolve(host, *args, **kwargs)

    def check_address(sock: socket.socket, address: object) -> None:
        if sock.family == socket.AF_UNIX:
            return
        if not isinstance(address, tuple) or not address or not _loopback(address[0]):
            pytest.fail("Offline test attempted external connection")

    def local_connect(sock: socket.socket, address: object) -> None:
        check_address(sock, address)
        connect(sock, address)

    def local_connect_ex(sock: socket.socket, address: object) -> int:
        check_address(sock, address)
        return connect_ex(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", local_resolve)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", local_connect_ex)
