# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Closed checkpoint encoding with no dynamic class lookup or pickle fallback."""

import base64
import json
from typing import cast

from langgraph.types import Interrupt
from pydantic import JsonValue, TypeAdapter

from datakeel.core.errors import ValidationError

_JSON = TypeAdapter(JsonValue)
_INVALID = "Checkpoint value is outside the primitive serialization allowlist"
_PAIR = 2


def _pack(value: object) -> JsonValue:
    if value is None or type(value) in (bool, int, float, str):
        return cast("JsonValue", value)
    if type(value) in (list, tuple):
        items = cast("list[object] | tuple[object, ...]", value)
        return [type(value).__name__, [_pack(item) for item in items]]
    if type(value) is dict:
        entries = cast("dict[object, object]", value)
        if any(type(key) is not str for key in entries):
            raise ValidationError(_INVALID)
        return ["dict", {cast("str", key): _pack(item) for key, item in entries.items()}]
    if type(value) is bytes:
        return ["bytes", base64.b64encode(value).decode("ascii")]
    if type(value) is Interrupt:
        pause = cast("Interrupt[object]", value)
        if pause.response_schema is not None:
            raise ValidationError(_INVALID)
        return ["interrupt", [pause.id, _pack(pause.value)]]
    raise ValidationError(_INVALID)


def _unpack(value: JsonValue) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if not isinstance(value, list) or len(value) != _PAIR:
        raise ValidationError(_INVALID)
    tag, data = value
    if tag in ("list", "tuple") and isinstance(data, list):
        items = [_unpack(item) for item in data]
        return items if tag == "list" else tuple(items)
    if tag == "dict" and isinstance(data, dict):
        return {key: _unpack(item) for key, item in data.items()}
    if tag == "bytes" and isinstance(data, str):
        return base64.b64decode(data, validate=True)
    if (
        tag == "interrupt"
        and isinstance(data, list)
        and len(data) == _PAIR
        and isinstance(data[0], str)
    ):
        return Interrupt(_unpack(data[1]), id=data[0])
    raise ValidationError(_INVALID)


class PrimitiveSerializer:
    """Encode only primitives and the fixed framework interrupt bookkeeping envelope."""

    def dumps_typed(self, obj: object) -> tuple[str, bytes]:
        """Reject unregistered objects before producing an opaque binary payload."""
        return "json", json.dumps(_pack(obj), ensure_ascii=False, allow_nan=False).encode("utf-8")

    def loads_typed(self, data: tuple[str, bytes]) -> object:
        """Decode a closed format without importing or invoking arbitrary classes."""
        if data[0] != "json":
            raise ValidationError(_INVALID)
        return _unpack(_JSON.validate_json(data[1]))
