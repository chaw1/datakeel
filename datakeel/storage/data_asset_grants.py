# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional applications, approval grants and revocation history."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import (
    AssetApplication,
    AssetApplicationInput,
    AssetControlEvent,
    AssetGrant,
    AssetMutationContext,
)
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.storage.data_asset_rows import AssetApplicationRow, AssetControlRow, AssetGrantRow
from datakeel.storage.data_asset_store import asset_in_session
from datakeel.storage.database import Database


def application_in_session(session: Session, application_id: str) -> AssetApplication:
    """Read one application without leaking a persistence record."""
    row = session.get(AssetApplicationRow, application_id)
    if row is None:
        msg = f"Asset application not found: {application_id}"
        raise NotFoundError(msg)
    return AssetApplication.model_validate(row.payload)


def get_application(db: Database, application_id: str) -> AssetApplication:
    """Read an application's current approval progress."""
    with db.session() as session:
        return application_in_session(session, application_id)


def grant_in_session(session: Session, grant_id: str) -> AssetGrant:
    """Read one grant including revoked and expired grants."""
    row = session.get(AssetGrantRow, grant_id)
    if row is None:
        msg = f"Asset grant not found: {grant_id}"
        raise NotFoundError(msg)
    return AssetGrant.model_validate(row.payload)


def get_grant(db: Database, grant_id: str) -> AssetGrant:
    """Read the exact persistent authorization state."""
    with db.session() as session:
        return grant_in_session(session, grant_id)


def _control(
    session: Session,
    event: AssetControlEvent,
) -> None:
    session.add(
        AssetControlRow(
            id=event.id,
            asset_id=event.asset_id,
            operation_id=event.operation_id,
            payload=event.model_dump(mode="json"),
        )
    )


def _event(
    asset_id: str,
    subject_id: str,
    action: str,
    context: AssetMutationContext,
    now: datetime,
) -> AssetControlEvent:
    return AssetControlEvent(
        id=new_id(),
        asset_id=asset_id,
        subject_id=subject_id,
        operation_id=context.operation_id,
        actor=context.actor,
        action=action,
        occurred_at=now,
    )


def _replay(
    session: Session,
    context: AssetMutationContext,
    action: str,
    subject_id: str | None = None,
) -> AssetControlEvent | None:
    row = session.scalar(
        select(AssetControlRow).where(AssetControlRow.operation_id == context.operation_id)
    )
    if row is None:
        return None
    event = AssetControlEvent.model_validate(row.payload)
    if (
        event.actor != context.actor
        or event.action != action
        or (subject_id is not None and event.subject_id != subject_id)
    ):
        msg = "Asset control operation identity already binds another request"
        raise ConflictError(msg)
    return event


def _same_application(application: AssetApplication, body: AssetApplicationInput) -> None:
    expected = AssetApplicationInput(
        asset_id=application.asset_id,
        purpose=application.purpose,
        scopes=application.scopes,
        expires_at=application.expires_at,
    )
    if expected != body:
        msg = "Application operation identity already binds another request"
        raise ConflictError(msg)


def submit_application(
    db: Database,
    body: AssetApplicationInput,
    applicant: str,
    *,
    now: datetime | None = None,
    operation_id: str | None = None,
) -> AssetApplication:
    """Submit a future-dated request without granting any data access."""
    moment = now or utcnow()
    if not applicant.strip() or body.expires_at <= moment:
        msg = "An applicant and a future expiry are required"
        raise ValidationError(msg)
    context = AssetMutationContext(actor=applicant, operation_id=operation_id or new_id())
    with db.session() as session:
        db.lock_writes(session)
        replay = _replay(session, context, "apply")
        if replay:
            application = application_in_session(session, replay.subject_id)
            _same_application(application, body)
            return application
        asset = asset_in_session(session, body.asset_id)
        if asset.status != "published":
            msg = "Only published assets accept usage applications"
            raise ValidationError(msg)
        application = AssetApplication(
            id=new_id(),
            applicant=applicant,
            created_at=moment,
            **body.model_dump(),
        )
        session.add(
            AssetApplicationRow(
                id=application.id,
                asset_id=body.asset_id,
                payload=application.model_dump(mode="json"),
            )
        )
        _control(session, _event(body.asset_id, application.id, "apply", context, moment))
        session.commit()
        return application


def decide_application_in_session(
    session: Session,
    application_id: str,
    context: AssetMutationContext,
    *,
    approved: bool,
    now: datetime | None = None,
) -> AssetApplication:
    """Apply one controlled decision and create exactly one corresponding grant."""
    replay = _replay(session, context, "approved" if approved else "rejected", application_id)
    if replay:
        return application_in_session(session, replay.subject_id)
    row = session.scalar(
        select(AssetApplicationRow)
        .where(AssetApplicationRow.id == application_id)
        .with_for_update()
    )
    before = application_in_session(session, application_id)
    moment = now or utcnow()
    if before.status != "pending" or before.expires_at <= moment:
        msg = "Application is already decided or its requested expiry has passed"
        raise ConflictError(msg)
    grant = _make_grant(before, context.actor, moment) if approved else None
    after = before.model_copy(
        update={
            "status": "approved" if approved else "rejected",
            "decided_at": moment,
            "decided_by": context.actor,
            "grant_id": grant.id if grant else None,
        }
    )
    if row is not None:
        row.payload = after.model_dump(mode="json")
    if grant:
        session.add(
            AssetGrantRow(
                id=grant.id,
                asset_id=grant.asset_id,
                application_id=application_id,
                subject=grant.subject,
                payload=grant.model_dump(mode="json"),
            )
        )
    _control(session, _event(before.asset_id, application_id, after.status, context, moment))
    session.flush()
    return after


def _make_grant(application: AssetApplication, actor: str, now: datetime) -> AssetGrant:
    return AssetGrant(
        id=new_id(),
        application_id=application.id,
        asset_id=application.asset_id,
        subject=application.applicant,
        scopes=application.scopes,
        expires_at=application.expires_at,
        created_at=now,
        granted_by=actor,
    )


def revoke_grant_in_session(
    session: Session,
    grant_id: str,
    context: AssetMutationContext,
    *,
    now: datetime | None = None,
) -> AssetGrant:
    """Revoke a grant while preserving its original authorization and decision audit."""
    replay = _replay(session, context, "revoke", grant_id)
    if replay:
        return grant_in_session(session, replay.subject_id)
    row = session.scalar(
        select(AssetGrantRow).where(AssetGrantRow.id == grant_id).with_for_update()
    )
    before = grant_in_session(session, grant_id)
    moment = now or utcnow()
    after = (
        before
        if before.revoked_at is not None
        else before.model_copy(update={"revoked_at": moment, "revoked_by": context.actor})
    )
    if row is not None:
        row.payload = after.model_dump(mode="json")
    _control(session, _event(before.asset_id, grant_id, "revoke", context, moment))
    session.flush()
    return after


def list_applications(
    db: Database,
    asset_id: str | None = None,
    applicant: str | None = None,
) -> tuple[AssetApplication, ...]:
    """List current request progress by resource and/or applicant."""
    with db.session() as session:
        result = (
            AssetApplication.model_validate(row.payload)
            for row in session.scalars(select(AssetApplicationRow))
        )
        return tuple(
            sorted(
                (
                    item
                    for item in result
                    if (
                        (asset_id is None or item.asset_id == asset_id)
                        and (applicant is None or item.applicant == applicant)
                    )
                ),
                key=lambda item: (item.created_at, item.id),
            )
        )


def list_grants(
    db: Database,
    asset_id: str | None = None,
    subject: str | None = None,
) -> tuple[AssetGrant, ...]:
    """List grants including expired and revoked authorization evidence."""
    with db.session() as session:
        statement = select(AssetGrantRow)
        if asset_id is not None:
            statement = statement.where(AssetGrantRow.asset_id == asset_id)
        if subject is not None:
            statement = statement.where(AssetGrantRow.subject == subject)
        return tuple(
            sorted(
                (AssetGrant.model_validate(row.payload) for row in session.scalars(statement)),
                key=lambda item: (item.created_at, item.id),
            )
        )


def control_history(db: Database, asset_id: str) -> tuple[AssetControlEvent, ...]:
    """Read immutable application and grant decisions in time and ID order."""
    with db.session() as session:
        return tuple(
            sorted(
                (
                    AssetControlEvent.model_validate(row.payload)
                    for row in session.scalars(
                        select(AssetControlRow).where(AssetControlRow.asset_id == asset_id)
                    )
                ),
                key=lambda item: (item.occurred_at, item.id),
            )
        )
