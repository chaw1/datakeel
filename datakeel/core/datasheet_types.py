# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declare what each datasheet fact measures so numbers are checked against their meaning."""

from typing import Literal

from pydantic import JsonValue

DatasheetValueKind = Literal[
    "count",
    "ratio",
    "percent",
    "score",
    "bytes",
    "amount",
    "duration",
    "date",
    "name",
    "status",
    "text",
    "number",
    "record",
]

# Kinds whose numeric leaves carry that measurement; other kinds leave bare numbers untyped.
MEASURED_KINDS: frozenset[DatasheetValueKind] = frozenset(
    ("count", "ratio", "percent", "score", "bytes", "amount", "duration", "date")
)

_FIELD_TYPES: dict[str, tuple[DatasheetValueKind, str | None]] = {
    "dataset.name": ("name", None),
    "version.created_at": ("date", None),
    "manifest.file_count": ("count", "files"),
    "manifest.modalities": ("count", "files"),
    "manifest.total_bytes": ("bytes", "bytes"),
    "manifest.filenames": ("name", None),
    "quality.total": ("score", "points"),
    "quality.grade": ("status", None),
    "quality.dimensions": ("record", None),
    "quality.issues": ("record", None),
    "compliance.total": ("score", "points"),
    "compliance.issues": ("record", None),
    "lineage.operator": ("name", None),
    "lineage.run_state": ("status", None),
    "lineage.occurred_at": ("date", None),
    "assertions.count": ("count", "assertions"),
    "assertions.status_counts": ("count", "assertions"),
    "assertions.verification_counts": ("count", "assertions"),
    "assertions.predicate_counts": ("count", "assertions"),
    "assertions.inactive_count": ("count", "assertions"),
    "decisions.review": ("record", None),
    "decisions.action": ("status", None),
    "decisions.status": ("status", None),
    "decisions.actor": ("name", None),
    "decisions.reason": ("text", None),
    "kg.entities": ("record", None),
    "kg.relation_count": ("count", "relations"),
    "metadata.creator": ("name", None),
    "metadata.owner": ("name", None),
    "metadata.maintainer": ("name", None),
    "metadata.collection_date": ("date", None),
}


def fact_type(field: str, value: JsonValue) -> tuple[DatasheetValueKind, str | None]:
    """Use the declared field meaning, otherwise describe only the JSON shape of the value."""
    key = "manifest.filenames" if field.startswith("manifest.filenames.") else field
    if key in _FIELD_TYPES:
        return _FIELD_TYPES[key]
    if isinstance(value, bool):
        return ("status", None)
    if isinstance(value, int | float):
        return ("number", None)
    if isinstance(value, dict | list):
        return ("record", None)
    return ("text", None)
