# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Separate comparable dbt result evidence from the per-invocation run record."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

from pydantic import JsonValue

from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument, LineageEvent

# A successful model, seed or snapshot reports adapter receipts ("INSERT 3", "SELECT 120")
# as its message; only a non-success message explains an outcome.
_SUCCESS = frozenset({"success", "pass"})


def run_results(document: JsonDocument | None) -> dict[str, JsonDocument]:
    """Index result entries by resource identity, rejecting malformed arrays."""
    if document is None:
        return {}
    values = document.root.get("results", [])
    if not isinstance(values, list):
        msg = "dbt run_results.results must be an array"
        raise ValidationError(msg)
    result: dict[str, JsonDocument] = {}
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("unique_id"), str):
            msg = "dbt run result must have a unique_id"
            raise ValidationError(msg)
        result[str(value["unique_id"])] = JsonDocument(value)
    return result


def run_outcome(result: JsonDocument) -> JsonDocument:
    """Keep what a rerun of unchanged code and data reproduces: status and failures.

    Timings, thread names, adapter receipts and batch windows change on every
    invocation; they stay in the run record and never mark a catalog object changed.
    """
    status = result.root.get("status")
    outcome: dict[str, JsonValue] = {"status": status, "failures": result.root.get("failures")}
    if status not in _SUCCESS:
        outcome["message"] = result.root.get("message")
    return JsonDocument(outcome)


def _occurred_at(metadata: dict[str, JsonValue]) -> datetime:
    value = metadata.get("generated_at")
    try:
        moment = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        moment = None
    if moment is None:
        return datetime.now(UTC)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def run_record(
    source_id: str, document: JsonDocument | None, results: dict[str, JsonDocument]
) -> LineageEvent | None:
    """Record one dbt invocation once, keyed by its invocation identity."""
    if document is None:
        return None
    raw = document.root.get("metadata")
    metadata: dict[str, JsonValue] = raw if isinstance(raw, dict) else {}
    invocation = metadata.get("invocation_id")
    if not isinstance(invocation, str) or not invocation:
        encoded = json.dumps(document.root, sort_keys=True, default=str).encode()
        invocation = hashlib.sha256(encoded).hexdigest()
    entries: list[JsonValue] = [
        {key: value for key, value in item.root.items() if key != "compiled_code"}
        for item in results.values()
    ]
    statuses = Counter(str(item.root.get("status")) for item in results.values())
    return LineageEvent(
        idempotency_key=f"dbt-run:{source_id}:{invocation}",
        operator="DBT_RUN",
        source_module="dbt",
        source_ref=f"metadata:dbt:{source_id}",
        params={
            "dbt_run": {
                "invocation_id": invocation,
                "generated_at": metadata.get("generated_at"),
                "dbt_version": metadata.get("dbt_version"),
                "elapsed_time": document.root.get("elapsed_time"),
                "results": entries,
            }
        },
        quality={"statuses": dict(sorted(statuses.items()))},
        occurred_at=_occurred_at(metadata),
    )
