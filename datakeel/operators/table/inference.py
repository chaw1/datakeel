# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Infer column types using explicit name hints and finite observed values."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import TYPE_CHECKING

from datakeel.operators.text.pii_redact import EMAIL, PHONE

if TYPE_CHECKING:
    from datakeel.operators.table.models import ColumnType, PiiKind
    from datakeel.operators.table.params import ProfileParams

_INTEGER = re.compile(r"[+-]?\d+\Z")
_AMOUNT = re.compile(r"[+-]?[$€£¥]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\Z")
_DATE = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}\Z")
_AMOUNT_NAMES = {"amount", "price", "cost", "revenue", "total", "balance", "salary"}
_PHONE_NAMES = {"phone", "mobile", "telephone", "tel", "contact", "手机号", "电话"}
_TIME_NAMES = {"time", "date", "timestamp", "datetime", "epoch", "unix", "ts"}
_COMPACT_MOBILE = re.compile(r"1[3-9]\d{9}\Z")
_MIN_PHONE_DIGITS = 10
_MAX_PHONE_DIGITS = 15


def _name_tokens(name: str) -> tuple[str, ...]:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return tuple(word for word in re.split(r"[_\W]+", words.casefold()) if word)


def is_identifier(name: str) -> bool:
    """Recognize explicit identifier-like names without assuming uniqueness."""
    tokens = _name_tokens(name)
    return bool(tokens) and (
        tokens[-1] in {"id", "uuid", "code"}
        or name.casefold() in {"sku", "serial", "serial_number"}
    )


def numeric_value(value: str) -> float | None:
    """Parse one finite number while rejecting infinities and nonnumeric values."""
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def amount_value(value: str) -> float | None:
    """Parse an unambiguous currency value with optional thousands grouping."""
    if not _AMOUNT.fullmatch(value):
        return None
    return numeric_value(re.sub(r"[$€£¥,\s]", "", value))


def _date_kind(value: str) -> ColumnType | None:
    if _DATE.fullmatch(value):
        try:
            datetime.fromisoformat(value.replace("/", "-"))
        except ValueError:
            return None
        return "date"
    if "T" not in value and " " not in value:
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return "datetime"


def _numeric_or_category(name: str, values: tuple[str, ...], params: ProfileParams) -> ColumnType:
    amount_name = bool(set(re.split(r"[_\W]+", name.casefold())) & _AMOUNT_NAMES)
    amount_symbol = any(any(symbol in value for symbol in "$€£¥") for value in values)
    if (amount_name or amount_symbol) and all(amount_value(value) is not None for value in values):
        return "amount"
    finite = all(numeric_value(value) is not None for value in values)
    if finite and all(_INTEGER.fullmatch(value) for value in values):
        return "integer"
    if finite:
        return "number"
    distinct = len(set(values))
    if distinct <= params.enum_max_values and distinct / len(values) <= params.enum_max_ratio:
        return "enum"
    return "string"


def infer_type(name: str, values: tuple[str, ...], params: ProfileParams) -> ColumnType:
    """Infer a conservative type only when every nonempty value agrees."""
    if not values:
        return "empty"
    if is_identifier(name):
        return "identifier"
    if all(value.casefold() in {"true", "false", "yes", "no"} for value in values):
        return "boolean"
    dates = {_date_kind(value) for value in values}
    if None not in dates:
        return "datetime" if "datetime" in dates else "date"
    return _numeric_or_category(name, values, params)


def value_family(value: str) -> str:
    """Group compatible scalar types for conservative majority-type findings."""
    if numeric_value(value) is not None or amount_value(value) is not None:
        return "numeric"
    if _date_kind(value) is not None:
        return "date"
    if value.casefold() in {"true", "false", "yes", "no"}:
        return "boolean"
    return "string"


def pii_kinds(name: str, values: tuple[str, ...]) -> tuple[PiiKind, ...]:
    """Reuse contact regexes while excluding explicit IDs and date/time columns."""
    kinds: list[PiiKind] = []
    if any(EMAIL.search(value) for value in values):
        kinds.append("email")
    tokens = _name_tokens(name)
    scalar_name = (
        is_identifier(name)
        or bool(set(tokens) & (_TIME_NAMES | _AMOUNT_NAMES))
        or bool(tokens and tokens[-1] == "at")
    )
    phone_name = bool(set(tokens) & _PHONE_NAMES)
    if any(_phone_value(value, phone_name=phone_name, scalar_name=scalar_name) for value in values):
        kinds.append("phone")
    return tuple(kinds)


def _phone_value(value: str, *, phone_name: bool, scalar_name: bool) -> bool:
    if _date_kind(value) is not None:
        return False
    integer = _INTEGER.fullmatch(value) is not None
    if not integer and (numeric_value(value) is not None or amount_value(value) is not None):
        return False
    if integer and scalar_name and not phone_name and not value.startswith("+"):
        return False
    return any(
        _phone_match(match.group(), value, phone_name=phone_name) for match in PHONE.finditer(value)
    )


def _phone_match(text: str, value: str, *, phone_name: bool) -> bool:
    digits = sum(character.isdigit() for character in text)
    if digits > _MAX_PHONE_DIGITS:
        return False
    if phone_name:
        return True
    if text.isdigit() and text == value:
        return _COMPACT_MOBILE.fullmatch(text) is not None
    return digits >= _MIN_PHONE_DIGITS
