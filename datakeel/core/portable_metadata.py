# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Remove storage implementation details and credential fields from portable metadata."""

import re
from urllib.parse import parse_qsl, urlsplit

from pydantic import JsonValue

_PRIVATE_KEYS = frozenset(
    {
        "path",
        "object_key",
        "password",
        "passwd",
        "token",
        "api_key",
        "access_key",
        "secret_key",
        "private_key",
        "authorization",
        "credentials",
        "storage_uri",
        "api_token",
        "client_secret",
        "access_key_id",
        "secret_access_key",
        "session_token",
        "bearer",
        "auth",
        "secret",
        "session_key",
    }
)
_PRIVATE_SUFFIXES = tuple(key.replace("_", "") for key in _PRIVATE_KEYS)


def portable_metadata(metadata: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Recursively exclude physical locations and authentication material from metadata."""
    return {key: _portable(value) for key, value in metadata.items() if not _private(key, value)}


def _private(key: str, value: JsonValue) -> bool:
    if _private_key(key):
        return True
    if not isinstance(value, str):
        return False
    location = value.strip()
    return (
        location.startswith(("/", "\\", "~/", "~\\"))
        or location[1:3] in {":\\", ":/"}
        or _credential_url(location)
    )


def _private_key(key: str) -> bool:
    compact = _compact_key(key)
    return (
        "credential" in compact
        or "password" in compact
        or any(compact.endswith(suffix) for suffix in _PRIVATE_SUFFIXES)
    )


def _portable(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return portable_metadata(value)
    if isinstance(value, list):
        return [_portable(item) for item in value if not _private("", item)]
    return value


def _credential_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme.casefold() in {"file", "s3", "s3a", "s3n"}
            or bool(parsed.username or parsed.password)
            or any(
                _compact_key(key) in {"sig", "key"}
                or _private_key(key)
                or "signature" in _compact_key(key)
                for key, _value in (
                    parse_qsl(parsed.query, keep_blank_values=True)
                    + parse_qsl(parsed.fragment, keep_blank_values=True)
                )
            )
        )
    except ValueError:
        return True


def _compact_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())
