# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise the real selected-version action and expose its existing selection ceiling."""

from time import perf_counter

from pydantic import ValidationError as SchemaValidationError
from sqlalchemy import select

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.storage.database import VersionRow
from scripts.scale_bench.models import BenchModel, Context

MAX_SELECTION = 10_000


class VersionMeasurement(BenchModel):
    """Separate full manifest persistence from the controlled action's actual capacity."""

    before: str
    after: str
    files: int
    prepare_seconds: float
    execute_seconds: float
    full_selection_rejected: bool
    rejection_seconds: float
    persistence_only: bool = False


def measure_selection_rejection(context: Context, identifier: str) -> float:
    """Time the real public schema's refusal above its existing selection limit."""
    started = perf_counter()
    try:
        prepare_action(
            context.db,
            "create_version_from_selection",
            JsonDocument({"selection": {"dataset_id": identifier, "limit": context.scale.files}}),
        )
    except (SchemaValidationError, ValidationError):
        return perf_counter() - started
    message = "Public version action unexpectedly accepted a selection above its declared ceiling"
    raise AssertionError(message)


def _metadata_snapshot(context: Context, identifier: str, before: str) -> str:
    with context.db.session() as session:
        manifest = session.scalar(select(VersionRow.manifest).where(VersionRow.id == before))
        row = VersionRow(dataset_id=identifier, manifest=manifest)
        session.add(row)
        session.commit()
        return row.id


def generate(context: Context, identifier: str) -> VersionMeasurement:
    """Generate a public selected version, or measure metadata persistence for the L extreme."""
    with context.db.session() as session:
        before = session.scalars(
            select(VersionRow.id)
            .where(VersionRow.dataset_id == identifier)
            .order_by(VersionRow.created_at, VersionRow.id)
        ).one()
    oversized = context.scale.files > MAX_SELECTION
    rejection = measure_selection_rejection(context, identifier) if oversized else 0.0
    if context.config.size == "L":
        started = perf_counter()
        after = _metadata_snapshot(context, identifier, before)
        return VersionMeasurement(
            before=before,
            after=after,
            files=context.scale.files,
            prepare_seconds=0,
            execute_seconds=perf_counter() - started,
            full_selection_rejected=oversized,
            rejection_seconds=rejection,
            persistence_only=True,
        )
    selection: dict[str, object] = {
        "dataset_id": identifier,
        "version_ids": [before],
        "limit": min(MAX_SELECTION, context.scale.files),
    }
    if oversized:
        selection["filters"] = [
            {"field": "filename", "operator": "contains", "value": "file-00000"}
        ]
    started = perf_counter()
    plan = prepare_action(
        context.db,
        "create_version_from_selection",
        JsonDocument.model_validate({"selection": selection}),
    )
    prepared = perf_counter() - started
    started = perf_counter()
    run = execute_plan(context.db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    outputs = (
        [ref for ref in run.receipt.outputs if ref.asset_type == "version"]
        if (run.receipt is not None)
        else []
    )
    if run.status != "SUCCEEDED" or len(outputs) != 1:
        message = "Controlled version action did not publish exactly one version"
        raise AssertionError(message)
    return VersionMeasurement(
        before=before,
        after=outputs[0].asset_id,
        files=len(plan.manifest.objects),
        prepare_seconds=prepared,
        execute_seconds=perf_counter() - started,
        full_selection_rejected=oversized,
        rejection_seconds=rejection,
    )
