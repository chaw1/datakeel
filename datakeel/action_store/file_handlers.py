# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""File-state lifecycle adapters; the caller owns the transaction and audit publication."""

from sqlalchemy.orm import Session

from datakeel.actions.declarations import ActionFrame, required
from datakeel.actions.models import ActionImpact, ActionPlan, OperationResult
from datakeel.actions.parameters import selection_for
from datakeel.actions.receipts import receipt as build_receipt
from datakeel.core.errors import ConflictError
from datakeel.dataset_store.file_state import apply_file_state
from datakeel.storage.action_selection import dataset_id_for
from datakeel.storage.action_snapshot import snapshot_digest
from datakeel.storage.action_targets import current_manifest
from datakeel.storage.evidence_actions import action_manifest


def prepare(_session: Session, frame: ActionFrame) -> ActionFrame:
    """Retain canonical selection validation before materialising targets."""
    selection_for(frame.params)
    return frame


def manifest(session: Session, frame: ActionFrame) -> ActionFrame:
    """Freeze the full selection, preserving ObjectSet 1.0 membership semantics."""
    value = (
        current_manifest(session, frame.plan, frame.params)
        if frame.plan
        else action_manifest(session, frame.params)
    )
    return frame.model_copy(update={"manifest": value})


def snapshot(session: Session, frame: ActionFrame) -> ActionFrame:
    """Bind actual file revisions using the historical state-digest algorithm."""
    manifest = required(frame.manifest)
    return frame.model_copy(
        update={"state_digest": snapshot_digest(session, frame.params, manifest)}
    )


def references(_session: Session, frame: ActionFrame) -> ActionFrame:
    """File-selection plans have no supplementary parameter references."""
    return frame


def impact(_session: Session, frame: ActionFrame) -> ActionFrame:
    """Account for every frozen target and byte."""
    manifest = required(frame.manifest)
    return frame.model_copy(
        update={
            "impact": ActionImpact(
                object_count=len(manifest.objects),
                total_bytes=manifest.total_bytes,
                external=False,
            )
        }
    )


def quarantine(session: Session, frame: ActionFrame) -> ActionFrame:
    """Apply the quarantine assignment inside the existing owning transaction."""
    return _assign(session, frame, value=True)


def unquarantine(session: Session, frame: ActionFrame) -> ActionFrame:
    """Apply the inverse assignment inside the same owning transaction."""
    return _assign(session, frame, value=False)


def _assign(session: Session, frame: ActionFrame, *, value: bool) -> ActionFrame:
    plan = required(frame.plan)
    change_file_state(session, plan, quarantined=value)
    return frame.model_copy(
        update={
            "result": OperationResult(outputs=[item.asset_ref for item in plan.manifest.objects])
        }
    )


def synchronous(_session: Session, frame: ActionFrame) -> ActionFrame:
    """Synchronous file-state handlers have no pending worker or deferred work."""
    if frame.result and (frame.result.task_id or frame.result.deferred):
        msg = "Synchronous action cannot defer completion"
        raise ConflictError(msg)
    return frame


# Both phases have no external resources; the owning transaction handles rollback.
rollback = references


def receipt(_session: Session, frame: ActionFrame) -> ActionFrame:
    """Build the existing attributed receipt without publishing or committing it."""
    plan, result = required(frame.plan), required(frame.result)
    return frame.model_copy(
        update={"event": build_receipt(plan, frame.run_id, result.outputs, error=frame.error)}
    )


def change_file_state(
    session: Session, plan: ActionPlan, *, quarantined: bool | None = None, deleted: bool = False
) -> None:
    """Update each unique selected file with an explicit revision increment."""
    seen: set[tuple[str, str]] = set()
    for item in plan.manifest.objects:
        identity = (dataset_id_for(item), item.asset_ref.asset_id)
        if identity in seen:
            continue
        seen.add(identity)
        apply_file_state(
            session,
            identity[0],
            identity[1],
            item.state_revision,
            quarantined=quarantined,
            deleted=deleted,
        )
