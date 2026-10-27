# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stable fact identities and conservative public values for dataset documentation."""

import hashlib
import ipaddress
import re
from datetime import datetime
from typing import cast
from urllib.parse import urlsplit

from pydantic import JsonValue, TypeAdapter

from datakeel.core.datasheet_models import DatasheetChapter, DatasheetFact

_PRIVATE_KEY = re.compile(
    r"(?:password|passwd|secret|token|credential|authorization|private.?key|object.?key|path|endpoint)",
    re.IGNORECASE,
)
_LOCAL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|(?<![\w/])/(?:[\w.~-]+/?)+)")
_URL = re.compile(r"(?:https?|file)://[^\s<>\"']+")
_JSON = TypeAdapter(JsonValue)


def _private_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme == "file"
            or parsed.username
            or parsed.password
            or _PRIVATE_KEY.search(parsed.query)
        ):
            return True
        host = parsed.hostname or ""
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
            (".local", ".localhost", ".lan", ".internal")
        ):
            return True
        try:
            return ipaddress.ip_address(host).is_private
        except ValueError:
            return False
    except ValueError:
        return True


def _safe_text(value: str) -> bool:
    urls = _URL.findall(value)
    return not (
        any(_private_url(url) for url in urls)
        or _LOCAL_PATH.search(_URL.sub("", value))
        or re.search(
            r"\b(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16})"
            r"|-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----",
            value,
            re.IGNORECASE,
        )
    )


def public_value(value: object) -> JsonValue | None:
    """Omit credential-shaped keys, local locations and credential-bearing strings."""
    if isinstance(value, str):
        return value if _safe_text(value) else None
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, child in cast("dict[object, object]", value).items():
            if isinstance(key, str) and not _PRIVATE_KEY.search(key):
                cleaned = public_value(child)
                if cleaned is not None:
                    result[key] = cleaned
        return result
    if isinstance(value, list | tuple):
        return [
            cleaned
            for child in cast("list[object] | tuple[object, ...]", value)
            if (cleaned := public_value(child)) is not None
        ]
    return _JSON.validate_python(value)


def make_fact(
    chapter: DatasheetChapter,
    source_type: str,
    source_id: str,
    field: str,
    value: object,
    recorded_at: datetime,
) -> DatasheetFact | None:
    """Bind a safe value to the deterministic identity of its exact source field."""
    cleaned = public_value(value)
    if cleaned is None:
        return None
    identity = f"{source_type}\0{source_id}\0{field}"
    return DatasheetFact(
        id="fact-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        chapter=chapter,
        source_type=source_type,
        source_id=source_id,
        field=field,
        value=cleaned,
        recorded_at=recorded_at,
    )
