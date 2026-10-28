# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve completed export artifacts under current source-data authorization."""

from pathlib import Path

from sqlalchemy import select

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.storage.action_access import authorize_plans_in_session
from datakeel.storage.action_rows import ActionRunRow
from datakeel.storage.action_store import locked_plan, run_view
from datakeel.storage.database import Database, data_dir


def completed_export(db: Database, plan_id: str, *, access: AccessContext | None = None) -> Path:
    """Return only the filename recorded by a successful authorized export receipt."""
    with db.session() as session:
        db.lock_writes(session)
        plan = locked_plan(session, plan_id)[1]
        authorize_plans_in_session(session, (plan,), access)
        row = session.scalar(
            select(ActionRunRow).where(
                ActionRunRow.plan_id == plan_id, ActionRunRow.status == "SUCCEEDED"
            )
        )
        if plan.action_type != "export_dataset" or row is None:
            message = "Completed export not found"
            raise NotFoundError(message)
        receipt = run_view(row).receipt
        details = JsonDocument.model_validate(receipt.quality if receipt else {}).root.get(
            "details"
        )
        filename = details.get("filename") if isinstance(details, dict) else None
        session.commit()
    return _artifact(filename if isinstance(filename, str) else "")


def _artifact(filename: str) -> Path:
    root = data_dir() / "exports"
    target = root / filename
    if (
        not filename
        or Path(filename).name != filename
        or "\\" in filename
        or target.is_symlink()
        or not root.resolve().is_relative_to(data_dir())
        or not target.is_file()
    ):
        message = "Export artifact is missing or outside the controlled directory"
        raise NotFoundError(message)
    return target
