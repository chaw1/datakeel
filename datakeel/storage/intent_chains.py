# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist and read action chains; plans and runs remain the authoritative history."""

from collections.abc import Sequence

from sqlalchemy import select

from datakeel.action_store.lifecycle import get_runs_by_plan_ids
from datakeel.actions.models import ActionRun
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.intent_models import ActionChain
from datakeel.core.models import utcnow
from datakeel.storage.database import Database
from datakeel.storage.intent_rows import ActionChainRow

LEASE_SECONDS = 600


def save_chain(db: Database, chain: ActionChain, *, release: bool = False) -> ActionChain:
    """Insert or replace one chain snapshot with a fresh update time."""
    value = chain.model_copy(update={"updated_at": utcnow()})
    with db.session() as session:
        db.lock_writes(session)
        row = session.scalar(
            select(ActionChainRow).where(ActionChainRow.id == value.id).with_for_update()
        )
        if row is None:
            row = ActionChainRow(id=value.id, conversation_id=value.conversation_id)
            session.add(row)
        row.actor = value.actor
        row.updated_at = value.updated_at.timestamp()
        row.payload = value.model_dump(mode="json")
        if release:
            row.lease_until = 0.0
        session.commit()
    return value


def claim_chain(db: Database, chain_id: str, actor: str) -> ActionChain:
    """Let one confirmation advance a chain at a time; a stale lease expires."""
    now = utcnow().timestamp()
    with db.session() as session:
        db.lock_writes(session)
        row = session.scalar(
            select(ActionChainRow).where(ActionChainRow.id == chain_id).with_for_update()
        )
        if row is None:
            message = "Action chain was not found"
            raise NotFoundError(message)
        chain = ActionChain.model_validate(row.payload)
        if chain.actor != actor:
            message = "Action chains can only be run by the person who asked for them"
            raise AuthorizationError(message)
        if (row.lease_until or 0.0) > now:
            message = "This chain is already being run"
            raise ConflictError(message)
        row.lease_until = now + LEASE_SECONDS
        session.commit()
    return chain


def plan_runs(db: Database, plan_ids: list[str]) -> dict[str, list[ActionRun]]:
    """Read every attempt of the given plans, oldest first."""
    return get_runs_by_plan_ids(db, plan_ids, newest_first=False)


def get_chain(db: Database, chain_id: str, *, actor: str | None = None) -> ActionChain:
    """Read one chain; a different person cannot read or run someone else's chain."""
    chain = get_chains_by_ids(db, (chain_id,)).get(chain_id)
    if chain is None:
        message = "Action chain was not found"
        raise NotFoundError(message)
    if actor is not None and actor != chain.actor:
        message = "Action chains can only be run by the person who asked for them"
        raise AuthorizationError(message)
    return chain


def list_chains(db: Database, conversation_id: str) -> list[ActionChain]:
    """List one conversation's chains in creation order."""
    with db.session() as session:
        rows = session.scalars(
            select(ActionChainRow)
            .where(ActionChainRow.conversation_id == conversation_id)
            .order_by(ActionChainRow.updated_at, ActionChainRow.id)
        )
        chains = [ActionChain.model_validate(row.payload) for row in rows]
    return sorted(chains, key=lambda chain: chain.created_at)


def get_chains_by_ids(db: Database, chain_ids: Sequence[str]) -> dict[str, ActionChain]:
    """Read only the requested chain snapshots in one read-only query."""
    if not chain_ids:
        return {}
    statement = select(ActionChainRow).where(ActionChainRow.id.in_(chain_ids))
    with db.session() as session:
        rows = session.scalars(statement)
        return {row.id: ActionChain.model_validate(row.payload) for row in rows}
