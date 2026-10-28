# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read standards and mappings from their authoritative append-only events."""

from sqlalchemy.orm import Session

from datakeel.core.catalog_canonical import document_hash
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.core.standard_history_models import (
    StandardsHistory,
    StandardsRevision,
    StandardsState,
)
from datakeel.core.standard_models import (
    CodeList,
    ColumnMapping,
    FieldStandard,
    StandardsContract,
    StandardStatus,
)
from datakeel.storage.catalog_locks import lock_catalog
from datakeel.storage.database import Database
from datakeel.storage.events import all_events


def revisions_in_session(session: Session) -> tuple[StandardsRevision, ...]:
    """Replay typed snapshots rather than trusting a disposable secondary projection."""
    revisions = [
        StandardsRevision.model_validate(event.params["standards_revision"])
        for event in all_events(session)
        if event.operator == "STANDARDS_CHANGE" and "standards_revision" in event.params
    ]
    return tuple(sorted(revisions, key=lambda value: value.revision))


def state_in_session(session: Session, revision: int | None = None) -> StandardsState:
    """Read current or historical semantics under the caller's transaction."""
    revisions = revisions_in_session(session)
    if revision == 0 or (revision is None and not revisions):
        return StandardsState()
    for item in reversed(revisions):
        if revision is None or item.revision == revision:
            return StandardsState(
                revision=item.revision, contract=item.contract, mappings=item.mappings
            )
    msg = f"Standards revision not found: {revision}"
    raise NotFoundError(msg)


def standards_state(session: Session) -> str:
    """Bind every revision and confirmed association to invalidate stale action plans."""
    lock_catalog(session)
    return document_hash(JsonDocument(state_in_session(session).model_dump(mode="json")))


def get_contract(db: Database) -> StandardsContract:
    """Return the effective validated YAML-compatible contract."""
    with db.session() as session:
        return state_in_session(session).contract


def list_mappings(db: Database) -> tuple[ColumnMapping, ...]:
    """Return only human-confirmed mappings, never inferred candidates."""
    with db.session() as session:
        return state_in_session(session).mappings


def history(db: Database) -> StandardsHistory:
    """Expose committed action attribution and complete historical snapshots."""
    with db.session() as session:
        return StandardsHistory(revisions=revisions_in_session(session))


def list_standards(
    db: Database, search: str = "", status: StandardStatus | None = None
) -> tuple[FieldStandard, ...]:
    """Search bilingual names, stable codes, definitions, aliases and owners."""
    needle = search.casefold()
    return tuple(
        item
        for item in get_contract(db).standards
        if (status is None or item.status == status)
        and needle
        in " ".join(
            (item.code, item.name_zh, item.name_en, item.description, item.owner, *item.aliases)
        ).casefold()
    )


def list_code_lists(
    db: Database, search: str = "", status: StandardStatus | None = None
) -> tuple[CodeList, ...]:
    """Search reference code lists by name, code and bilingual entry labels."""
    needle = search.casefold()
    return tuple(
        item
        for item in get_contract(db).code_lists
        if (status is None or item.status == status)
        and needle
        in " ".join(
            (
                item.code,
                item.name,
                *(entry.label_zh + " " + entry.label_en for entry in item.entries),
            )
        ).casefold()
    )
