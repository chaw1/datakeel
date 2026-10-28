# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create approved local export artifacts without network transmission."""

import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.parameters import ExportParams
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import AssetRef
from datakeel.core.settings import get_settings
from datakeel.lineage.exports import export_croissant, export_openlineage
from datakeel.lineage.service import graph
from datakeel.storage.action_selection import selected_files
from datakeel.storage.data_asset_access import require_access_in_session
from datakeel.storage.database import DatasetRow, data_dir
from datakeel.storage.datasets import dataset_dict
from datakeel.storage.events import all_events


def export_path(destination: str) -> Path:
    """Resolve a new export filename while rejecting traversal and symlink escape."""
    if not destination or Path(destination).name != destination or "\\" in destination:
        msg = "Export destination must be a filename"
        raise ValidationError(msg)
    root = data_dir() / "exports"
    root.mkdir(parents=True, exist_ok=True)
    target = root / destination
    if not root.resolve().is_relative_to(data_dir()) or target.is_symlink():
        msg = "Export destination escapes the controlled exports directory"
        raise ValidationError(msg)
    if target.exists():
        msg = "Export destination already exists"
        raise ConflictError(msg)
    return target


def export_action(session: Session, plan: ActionPlan, params: ExportParams) -> OperationResult:
    """Write the reviewed dataset export as one exclusive local artifact."""
    dataset = session.get(DatasetRow, params.dataset_id)
    if dataset is None:
        msg = "Export dataset not found"
        raise NotFoundError(msg)
    require_access_in_session(
        session,
        (AssetRef(asset_id=params.dataset_id),),
        AccessContext(actor=plan.context.actor, entry="export", scope="export"),
        record=False,
    )
    target = export_path(params.destination or f"{plan.id}.json")
    if params.format == "croissant":
        data = {**dataset_dict(dataset), "base_url": get_settings().base_url}
        payload = export_croissant(data, selected_files(session, plan)).model_dump(mode="json")
    else:
        events = graph(all_events(session), dataset.id).events
        payload = [value.model_dump(mode="json") for value in export_openlineage(events)]
    content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    inode, size = _write_export(target, content)
    return OperationResult(
        outputs=[
            AssetRef(asset_type="artifact", asset_id=f"export:{plan.id}", display_name=target.name)
        ],
        generated_file=target,
        generated_inode=inode,
        details={"filename": target.name, "bytes": size},
    )


def rollback_export(result: OperationResult | None) -> None:
    """Remove only the exact exclusively-created artifact after a failed transaction."""
    if result is None or result.generated_file is None:
        return
    _remove_owned(result.generated_file, result.generated_inode)


def _remove_owned(path: Path, inode: int | None) -> None:
    if path.exists() and not path.is_symlink() and path.stat().st_ino == inode:
        path.unlink()


def _write_export(path: Path, content: str) -> tuple[int, int]:
    inode = None
    try:
        with path.open("x", encoding="utf-8") as output:
            inode = os.fstat(output.fileno()).st_ino
            output.write(content)
        return inode, path.stat().st_size
    except (OSError, ValueError):
        _remove_owned(path, inode)
        raise
