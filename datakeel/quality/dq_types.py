# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Match reflected column types to the rule kinds that can evaluate their values."""

from typing import Literal

from datakeel.core.dq_models import DqRule
from datakeel.core.errors import ValidationError

type ColumnCategory = Literal[
    "numeric",
    "text",
    "uuid",
    "boolean",
    "temporal",
    "time",
    "json",
    "array",
    "binary",
    "interval",
    "other",
    "dynamic",
]

_POSTGRES_TYPES: dict[str, ColumnCategory] = {
    **dict.fromkeys(
        (
            "SMALLINT",
            "INTEGER",
            "BIGINT",
            "INT",
            "INT2",
            "INT4",
            "INT8",
            "NUMERIC",
            "DECIMAL",
            "REAL",
            "FLOAT",
            "FLOAT4",
            "FLOAT8",
            "DOUBLE PRECISION",
        ),
        "numeric",
    ),
    **dict.fromkeys(
        ("TEXT", "VARCHAR", "CHAR", "CHARACTER", "CHARACTER VARYING", "BPCHAR", "NAME", "CITEXT"),
        "text",
    ),
    **dict.fromkeys(("DATE", "TIMESTAMP", "TIMESTAMPTZ", "DATETIME"), "temporal"),
    **dict.fromkeys(("TIME", "TIMETZ"), "time"),
    **dict.fromkeys(("JSON", "JSONB"), "json"),
    **dict.fromkeys(("BOOLEAN", "BOOL"), "boolean"),
    "UUID": "uuid",
    "BYTEA": "binary",
    "INTERVAL": "interval",
    "ARRAY": "array",
}
_SCALAR: frozenset[ColumnCategory] = frozenset(
    {"numeric", "text", "uuid", "boolean", "temporal", "time", "dynamic"}
)
_REQUIREMENTS: dict[str, tuple[frozenset[ColumnCategory], str]] = {
    "unique": (_SCALAR, "a scalar column, not JSON, array, binary or interval"),
    "accepted_values": (
        frozenset({"numeric", "text", "uuid", "boolean", "dynamic"}),
        "a text, numeric, boolean or UUID column",
    ),
    "regex": (frozenset({"text", "uuid", "dynamic"}), "a text or UUID column"),
    "referential_integrity": (
        frozenset({"numeric", "text", "uuid", "temporal", "dynamic"}),
        "a text, numeric, UUID or date/timestamp column",
    ),
    "range": (frozenset({"numeric", "dynamic"}), "a numeric column"),
    "freshness": (frozenset({"temporal", "dynamic"}), "a DATE or TIMESTAMP column"),
    "distribution_drift": (frozenset({"numeric", "dynamic"}), "a numeric column"),
}
# Values compare as Python scalars; UUIDs arrive as canonical text.
_COMPARABLE: tuple[frozenset[ColumnCategory], ...] = (
    frozenset({"text", "uuid"}),
    frozenset({"numeric"}),
    frozenset({"temporal"}),
    frozenset({"boolean"}),
)


def column_category(type_name: str, dialect: str) -> ColumnCategory:
    """Classify a reflected type; SQLite columns stay dynamic apart from declared BLOBs."""
    name = " ".join(type_name.upper().split())
    base = name.split("(", 1)[0].strip()
    if dialect not in {"postgres", "postgresql"}:
        return "binary" if base == "BLOB" else "dynamic"
    if name.endswith("[]"):
        return "array"
    return _POSTGRES_TYPES.get(base, "other")


def nulls_only(rule: DqRule) -> bool:
    """Identify rules that only test NULL-ness and therefore never need cell values."""
    return rule.kind == "not_null" or (
        rule.kind == "distribution_drift" and rule.params.statistic == "null_rate"
    )


def check_column_types(
    rule: DqRule,
    column_type: str,
    dialect: str,
    reference_type: str | None = None,
) -> None:
    """Reject kinds whose values the target (and reference) column types cannot provide."""
    category = column_category(column_type, dialect)
    allowed, description = _REQUIREMENTS.get(rule.kind, (_SCALAR, ""))
    if not nulls_only(rule) and category not in allowed:
        msg = (
            f"{rule.kind} rules need {description}; column {rule.target.column} "
            f"has type {column_type}"
        )
        raise ValidationError(msg)
    if reference_type is None:
        return
    reference = column_category(reference_type, dialect)
    if reference not in allowed:
        msg = (
            f"Reference column {rule.params.reference_column} has unsupported type {reference_type}"
        )
        raise ValidationError(msg)
    if "dynamic" not in {category, reference} and not any(
        {category, reference} <= group for group in _COMPARABLE
    ):
        msg = (
            f"Reference column type {reference_type} is not comparable with "
            f"target column type {column_type}"
        )
        raise ValidationError(msg)
