# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist approved custom code through controlled actions and expose typed audit views."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.custom_operators import (
    CustomOperatorRun,
    CustomOperatorVersion,
    SubmitCustomOperatorParams,
    custom_reference,
)
from datakeel.core.custom_review import prepare_submission
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import AssetRef, LineageEvent, utcnow
from datakeel.storage.action_rows import ActionPlanRow, ApprovalRow
from datakeel.storage.action_store import locked_plan
from datakeel.storage.custom_rows import CustomOperatorRow, CustomRunRow
from datakeel.storage.database import Database
from datakeel.storage.events import append_event


def approve_custom_operator(
    session: Session, plan: ActionPlan, params: SubmitCustomOperatorParams
) -> OperationResult:
    """Publish the exact human-approved content after shared approval consumption."""
    prepared = prepare_submission(params)
    if prepared != params or params.parameter_schema is None or params.metadata_schema is None:
        msg = "Custom source review material does not match the approved content"
        raise ConflictError(msg)
    approval = session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == plan.id))
    if approval is None or approval.status != "APPROVED" or not approval.consumed:
        msg = "Custom operator publication requires a consumed human approval"
        raise ConflictError(msg)
    identifier = f"custom.{params.name}@{params.code_hash}"
    existing = session.get(CustomOperatorRow, identifier)
    if existing is None:
        version = CustomOperatorVersion(
            **params.model_dump(exclude={"parameter_schema", "metadata_schema"}),
            parameter_schema=params.parameter_schema,
            metadata_schema=params.metadata_schema,
            id=identifier,
            plan_id=plan.id,
            approved_by=approval.actor,
            approved_at=utcnow(),
        )
        session.add(
            CustomOperatorRow(
                id=identifier,
                name=params.name,
                code_hash=params.code_hash,
                payload=version.model_dump(mode="json"),
            )
        )
    elif CustomOperatorVersion.model_validate(existing.payload).modality != params.modality:
        msg = "A code version cannot change its approved modality"
        raise ConflictError(msg)
    return OperationResult(
        outputs=[
            AssetRef(asset_type="custom_operator", asset_id=identifier, version=params.code_hash)
        ],
        details={"operator": identifier, "code_hash": params.code_hash},
    )


def approved_in_session(session: Session, identifier: str) -> CustomOperatorVersion:
    """Require immutable registered content whose source still matches its digest."""
    name, code_hash = custom_reference(identifier)
    row = session.get(CustomOperatorRow, identifier)
    if row is None:
        msg = "Custom operator version is not approved"
        raise NotFoundError(msg)
    version = CustomOperatorVersion.model_validate(row.payload)
    current = prepare_submission(
        SubmitCustomOperatorParams.model_validate(
            version.model_dump(include={"name", "code", "modality"})
        )
    )
    if (
        (identifier, name, code_hash) != (version.id, version.name, version.code_hash)
        or (row.name, row.code_hash) != (name, code_hash)
        or current.code_hash != version.code_hash
        or current.parameter_schema != version.parameter_schema
        or current.metadata_schema != version.metadata_schema
    ):
        msg = "Approved custom operator content was modified"
        raise ConflictError(msg)
    return version


def get_custom_operator(
    db: Database, code_hash: str, name: str | None = None
) -> CustomOperatorVersion:
    """Read an approved version, requiring a name when its digest is ambiguous."""
    with db.session() as session:
        query = select(CustomOperatorRow).where(CustomOperatorRow.code_hash == code_hash)
        if name is not None:
            query = query.where(CustomOperatorRow.name == name)
        rows = list(session.scalars(query))
        if not rows:
            msg = "Custom operator version not found"
            raise NotFoundError(msg)
        if len(rows) > 1:
            msg = "Code digest has multiple operator names; specify name"
            raise ConflictError(msg)
        return approved_in_session(session, rows[0].id)


def list_custom_operators(db: Database) -> list[CustomOperatorVersion]:
    """List approved immutable versions in stable name and digest order."""
    with db.session() as session:
        return [
            approved_in_session(session, row.id)
            for row in session.scalars(select(CustomOperatorRow).order_by(CustomOperatorRow.id))
        ]


def list_custom_submissions(db: Database) -> list[ActionPlan]:
    """Expose full source and advisory checks through the existing reviewable plans."""
    with db.session() as session:
        return [
            locked_plan(session, row.id)[1]
            for row in session.scalars(
                select(ActionPlanRow)
                .where(ActionPlanRow.action_type == "submit_custom_operator")
                .order_by(ActionPlanRow.id)
            )
        ]


def list_custom_runs(db: Database, code_hash: str | None = None) -> list[CustomOperatorRun]:
    """Read durable successful and failed sandbox-attempt records."""
    with db.session() as session:
        query = select(CustomRunRow).order_by(CustomRunRow.id)
        if code_hash is not None:
            query = query.where(CustomRunRow.code_hash == code_hash)
        return [CustomOperatorRun.model_validate(row.payload) for row in session.scalars(query)]


def record_custom_run(db: Database, record: CustomOperatorRun, dataset_id: str) -> None:
    """Atomically retain an attempt and its audit lineage without publishing output assets."""
    with db.session() as session:
        db.lock_writes(session)
        session.add(
            CustomRunRow(
                id=record.id,
                code_hash=record.code_hash,
                task_id=record.task_id,
                payload=record.model_dump(mode="json"),
            )
        )
        append_event(
            session,
            LineageEvent(
                idempotency_key=f"custom-run:{record.id}",
                operator=record.operator,
                inputs=[
                    AssetRef(asset_id=dataset_id),
                    AssetRef(
                        asset_type="custom_operator",
                        asset_id=record.operator,
                        version=record.code_hash,
                    ),
                ],
                outputs=[AssetRef(asset_type="custom_operator_run", asset_id=record.id)],
                source_module="sandbox",
                source_ref=record.task_id,
                params={"params_digest": record.params_digest},
                quality={"custom_operator": record.model_dump(mode="json")},
                run_state="COMPLETED" if record.success else "FAILED",
            ),
        )
        session.commit()
