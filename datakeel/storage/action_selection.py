# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve frozen file references to storage records inside execution transactions."""

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import FileItem
from datakeel.ontology.models import FrozenManifest, FrozenObject
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.file_state import FileStateRow


def dataset_id_for(item: FrozenObject) -> str:
    """Resolve the owning dataset identifier recorded in the frozen object."""
    identifier = item.properties.get("dataset_id")
    if not isinstance(identifier, str):
        msg = "Frozen file has no owning dataset"
        raise ConflictError(msg)
    return identifier


def require_unique_file_sources(manifest: FrozenManifest) -> None:
    """Reject ambiguous file identities before one materialized record could overwrite another."""
    sources: dict[str, tuple[str, str | None]] = {}
    for item in manifest.objects:
        source = (dataset_id_for(item), item.asset_ref.version)
        prior = sources.setdefault(item.asset_ref.asset_id, source)
        if prior != source:
            msg = "Select one exact source version per asset before materializing files"
            raise ConflictError(msg)


def selected_files(session: Session, plan: ActionPlan) -> list[FileItem]:
    """Read exact manifest entries named by the already revalidated selection."""
    require_unique_file_sources(plan.manifest)
    selected: dict[str, FileItem] = {}
    for item in plan.manifest.objects:
        dataset_id = dataset_id_for(item)
        dataset = session.get(DatasetRow, dataset_id)
        if dataset is None:
            msg = "Selected dataset no longer exists"
            raise NotFoundError(msg)
        version_id = item.properties.get("version_id")
        version = session.get(VersionRow, version_id) if isinstance(version_id, str) else None
        manifest = version.manifest if version else dataset.files
        record = next((entry for entry in manifest if entry["id"] == item.asset_ref.asset_id), None)
        if record is None:
            msg = "Selected file no longer belongs to its frozen version"
            raise ConflictError(msg)
        selected[item.asset_ref.asset_id] = FileItem.model_validate(record)
    return list(selected.values())


def single_dataset(plan: ActionPlan) -> str:
    """Require one owning dataset before creating a version or pipeline task."""
    datasets = {dataset_id_for(item) for item in plan.manifest.objects}
    if len(datasets) != 1:
        msg = "This action requires a nonempty selection from one dataset"
        raise ConflictError(msg)
    return datasets.pop()


def change_file_state(session: Session, plan: ActionPlan) -> None:
    """Update each unique selected file with an explicit revision increment."""
    seen: set[tuple[str, str]] = set()
    for item in plan.manifest.objects:
        identity = (dataset_id_for(item), item.asset_ref.asset_id)
        if identity in seen:
            continue
        seen.add(identity)
        row = session.get(FileStateRow, identity, with_for_update=True)
        if row is None:
            row = FileStateRow(
                dataset_id=identity[0],
                file_id=identity[1],
                quarantined=False,
                deleted=False,
                revision=0,
            )
            session.add(row)
        if row.deleted or row.revision != item.state_revision:
            msg = "Selected file revision changed during execution"
            raise ConflictError(msg)
        if plan.action_type == "delete_files":
            row.deleted = True
        else:
            row.quarantined = plan.action_type == "quarantine_files"
        row.revision += 1
