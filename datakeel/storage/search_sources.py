# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stream public discovery fields with a legacy fallback for escaped JSON strings."""

from collections.abc import Iterator
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.core.models import FileItem
from datakeel.core.search_models import SearchKind, SearchQuery, SearchResult
from datakeel.storage.action_rows import ActionRunRow
from datakeel.storage.catalog_fields import read_fields
from datakeel.storage.catalog_rows import CatalogObjectRow
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.file_discovery import requires_python_files
from datakeel.storage.file_state import FileStateRow


def _file_sql(*, sqlite: bool) -> str:
    collation = "BINARY" if sqlite else '"C"'
    return (
        "SELECT f.id, f.name, f.dataset_id, f.version_id, "  # noqa: S608  # Fixed SQL fragments.
        "CASE WHEN s.deleted THEN 'deleted' WHEN s.quarantined THEN 'quarantined' "
        "ELSE 'normal' END AS status FROM ("
        "SELECT d.file_id AS id, d.name, d.dataset_id, d.version_id, "
        f"row_number() OVER (PARTITION BY d.file_id COLLATE {collation} "
        f"ORDER BY d.created_at, d.version_id COLLATE {collation}) AS priority "
        "FROM file_discovery AS d) AS f "
        "LEFT JOIN file_states AS s ON s.dataset_id = f.dataset_id AND s.file_id = f.id "
        "WHERE f.priority = 1"
    )


def _bounded_file_sql(*, sqlite: bool) -> str:
    non_ascii = (
        "(name GLOB '*[^ -~]*' OR id GLOB '*[^ -~]*')"
        if sqlite
        else "(name ~ '[^ -~]' OR id ~ '[^ -~]')"
    )
    collation = "BINARY" if sqlite else '"C"'
    # ASCII casefold/NFC equals SQL lower. Unicode candidates retain the exact Python
    # normalization/ranking path, so a shortlist cannot hide a higher-ranked match.
    return (
        f"WITH candidates AS ({_file_sql(sqlite=sqlite)}) "  # noqa: S608  # Fixed SQL fragments.
        f"SELECT * FROM (SELECT * FROM candidates WHERE NOT {non_ascii} "
        "AND (:needle = '' OR lower(id) LIKE :pattern ESCAPE '!' "
        "OR lower(name) LIKE :pattern ESCAPE '!') ORDER BY "
        "CASE WHEN lower(id) = :needle THEN 0 "
        "WHEN lower(id) LIKE :prefix ESCAPE '!' THEN 1 "
        "WHEN lower(name) = :needle THEN 2 "
        "WHEN lower(name) LIKE :prefix ESCAPE '!' THEN 3 ELSE 4 END, "
        f"lower(name) COLLATE {collation}, id COLLATE {collation} LIMIT :limit) AS bounded "
        f"UNION ALL SELECT * FROM candidates WHERE {non_ascii}"
    )


def _python_files(session: Session) -> Iterator[SearchResult]:
    states = {(row.dataset_id, row.file_id): row for row in session.scalars(select(FileStateRow))}
    seen: set[str] = set()
    collation = "BINARY" if session.get_bind().dialect.name == "sqlite" else "C"
    statement = select(VersionRow.id, VersionRow.dataset_id, VersionRow.manifest).order_by(
        VersionRow.created_at, VersionRow.id.collate(collation)
    )
    for version in session.execute(statement.execution_options(yield_per=1)):
        for raw in version.manifest:
            file = FileItem.model_validate(raw)
            if file.id in seen:
                continue
            seen.add(file.id)
            state = states.get((version.dataset_id, file.id))
            yield SearchResult(
                kind="file",
                id=file.id,
                name=file.filename,
                dataset_id=version.dataset_id,
                version_id=version.id,
                status="deleted"
                if state and state.deleted
                else "quarantined"
                if state and state.quarantined
                else "normal",
            )


def file_results(session: Session, query: SearchQuery) -> Iterator[SearchResult]:
    """Shortlist ASCII matches in SQL; preserve exact Unicode and earliest-version semantics."""
    if requires_python_files(session):
        yield from _python_files(session)
        return
    sqlite = session.get_bind().dialect.name == "sqlite"
    needle = query.q
    bounded = needle.isascii() and "\0" not in needle
    statement = _bounded_file_sql(sqlite=sqlite) if bounded else _file_sql(sqlite=sqlite)
    escaped = needle.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    parameters = {
        "needle": needle,
        "pattern": f"%{escaped}%",
        "prefix": f"{escaped}%",
        "limit": query.limit,
    }
    for row in session.execute(
        text(statement).execution_options(yield_per=100), parameters if bounded else {}
    ):
        yield SearchResult(
            kind="file",
            id=row.id,
            name=row.name,
            dataset_id=row.dataset_id,
            version_id=row.version_id,
            status=row.status,
        )


def dataset_results(session: Session) -> Iterator[SearchResult]:
    """Read dataset and version navigation without their large JSON payload columns."""
    datasets = dict(session.execute(select(DatasetRow.id, DatasetRow.name)).all())
    counts: dict[str, int] = {}
    for row in session.execute(
        select(VersionRow.id, VersionRow.dataset_id).order_by(VersionRow.created_at, VersionRow.id)
    ):
        counts[row.dataset_id] = counts.get(row.dataset_id, 0) + 1
        yield SearchResult(
            kind="version",
            id=row.id,
            name=(f"{datasets[row.dataset_id]} · v{counts[row.dataset_id]}"),
            dataset_id=row.dataset_id,
            version_id=row.id,
            status="immutable",
        )
    for identifier, name in datasets.items():
        yield SearchResult(
            kind="dataset",
            id=identifier,
            name=name,
            dataset_id=identifier,
            status="versioned" if identifier in counts else "empty",
        )


def other_results(session: Session) -> Iterator[SearchResult]:
    """Avoid validating unrelated catalog properties and action execution payloads."""
    statement = select(CatalogObjectRow).where(
        CatalogObjectRow.kind.in_(["table", "column", "metric", "term"])
    )
    for item in read_fields(session, statement):
        yield SearchResult(
            kind=cast("SearchKind", item.kind),
            id=item.identity,
            name=item.name,
            english_name=item.english_name,
        )
    for row in session.execute(
        select(ActionRunRow.id, ActionRunRow.action_type, ActionRunRow.status)
    ):
        yield SearchResult(kind="action_run", id=row.id, name=row.action_type, status=row.status)
