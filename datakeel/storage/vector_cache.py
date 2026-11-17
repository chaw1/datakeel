# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read and project mode-separated vector products only inside unified publications."""

from typing import cast

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session, SessionTransaction

from datakeel.core.vector_results import VectorCacheProduct
from datakeel.storage.database import Database
from datakeel.storage.vector_rows import VectorCacheRow

_LOCK_TRANSACTIONS = "datakeel.evidence_projection.lock_transactions"


@event.listens_for(Session, "after_commit")
def _promote_evidence_lock(session: Session) -> None:
    """A released savepoint transfers its locks to the parent transaction."""
    held = cast("set[SessionTransaction]", session.info.get(_LOCK_TRANSACTIONS, set()))
    nested = session.get_nested_transaction()
    if nested is not None and nested in held and nested.parent is not None:
        held.add(nested.parent)


@event.listens_for(Session, "after_transaction_end")
def _forget_evidence_lock(session: Session, transaction: SessionTransaction) -> None:
    """Discard ended identities, including rolled-back savepoints and Session.close()."""
    held = cast("set[SessionTransaction]", session.info.get(_LOCK_TRANSACTIONS, set()))
    held.discard(transaction)
    if not held:
        session.info.pop(_LOCK_TRANSACTIONS, None)


def vector_cached(
    db: Database, key: str, kind: str, *, mode: str = "fake", implementation: str = "we-e2-fake-v1"
) -> VectorCacheProduct | None:
    """Read only the exact mode/implementation namespace; never fall through across modes."""
    with db.session() as session:
        row = session.get(VectorCacheRow, f"{mode}:{implementation}:{kind}:{key}")
        if row is None:
            return None
        p = VectorCacheProduct.model_validate(row.payload)
        ok = (p.key, p.kind, p.mode, p.implementation) == (key, kind, mode, implementation)
        return p if ok else None


def project_vectors(
    session: Session, products: tuple[VectorCacheProduct, ...], event_id: str
) -> None:
    """Publish disposable entries in the same transaction as assertions and their bundle."""
    for product in products:
        key = f"{product.mode}:{product.implementation}:{product.kind}:{product.key}"
        row = session.get(VectorCacheRow, key)
        if row is None:
            session.add(
                VectorCacheRow(
                    namespace_key=key,
                    producer_event_id=event_id,
                    payload=product.model_dump(mode="json"),
                )
            )
        else:
            row.producer_event_id = event_id
            row.payload = product.model_dump(mode="json")


def vector_predecessors(
    session: Session, products: tuple[VectorCacheProduct, ...]
) -> tuple[str, ...]:
    """Bind replacement cache producers so missing or reordered replay is explicit."""
    if not products:
        return ()
    keys = [f"{item.mode}:{item.implementation}:{item.kind}:{item.key}" for item in products]
    return tuple(
        sorted(
            set(
                session.scalars(
                    select(VectorCacheRow.producer_event_id).where(
                        VectorCacheRow.namespace_key.in_(keys)
                    )
                )
            )
        )
    )


def lock_evidence(session: Session) -> None:
    """Deduplicate PostgreSQL lock SQL only while its acquiring transaction survives."""
    if session.get_bind().dialect.name != "postgresql":
        return
    transaction = session.get_nested_transaction() or session.get_transaction() or session.begin()
    held = cast("set[SessionTransaction]", session.info.get(_LOCK_TRANSACTIONS, set()))
    ancestor: SessionTransaction | None = transaction
    while ancestor is not None:
        if ancestor in held:
            return
        ancestor = ancestor.parent
    session.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtext(current_schema()), "
            "hashtext('evidence_projection'))"
        )
    )
    session.info.setdefault(_LOCK_TRANSACTIONS, set()).add(transaction)
