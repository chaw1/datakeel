# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expand and page manifests in SQL without deserializing every file into Python."""

import json
import unicodedata
from collections.abc import Iterator
from itertools import batched, islice

from sqlalchemy import text
from sqlalchemy.orm import Session

from datakeel.core.errors import NotFoundError
from datakeel.core.file_queries import FileQuery
from datakeel.core.models import FileItem
from datakeel.storage.file_discovery import begin_file_read, requires_python_files
from datakeel.storage.file_state import overlay_files


def _statement(*, sqlite: bool, version: bool) -> str:
    table, column = ("versions", "manifest") if version else ("datasets", "files")
    expand = (
        f"json_each(t.{column}) AS j"
        if sqlite
        else f"json_array_elements(t.{column}) WITH ORDINALITY AS j(value, ordinal)"
    )
    file_id = "json_extract(j.value, '$.id')" if sqlite else "j.value->>'id'"
    filename = "json_extract(j.value, '$.filename')" if sqlite else "j.value->>'filename'"
    modality = "json_extract(j.value, '$.modality')" if sqlite else "j.value->>'modality'"
    ordinal = "CAST(j.key AS INTEGER)" if sqlite else "j.ordinal"
    unicode_name = f"{filename} GLOB '*[^ -~]*'" if sqlite else f"{filename} ~ '[^ -~]'"
    return (
        f"SELECT j.value FROM {table} AS t, {expand} "  # noqa: S608  # Fixed SQL fragments.
        f"LEFT JOIN file_states AS s ON s.dataset_id = :dataset AND s.file_id = {file_id} "
        "WHERE t.id = :id AND (s.deleted IS NULL OR s.deleted = false) "
        f"AND (CAST(:modality AS TEXT) IS NULL OR {modality} = :modality) "
        f"AND (:q = '' OR lower({filename}) LIKE :pattern ESCAPE '!' OR {unicode_name}) "
        f"ORDER BY {ordinal} LIMIT :limit OFFSET :offset"
    )


def _require_manifest(session: Session, dataset_id: str, version: str | None) -> None:
    statement = (
        "SELECT id FROM versions WHERE id = :id AND dataset_id = :dataset"
        if version
        else "SELECT id FROM datasets WHERE id = :id"
    )
    found = session.scalar(text(statement), {"id": version or dataset_id, "dataset": dataset_id})
    if found is None:
        message = "Version not found" if version else "Dataset not found"
        raise NotFoundError(message)


def _python_filter(query: FileQuery) -> bool:
    return "\0" in query.q or (query.modality is not None and "\0" in query.modality)


def _fallback_rows(
    session: Session, dataset_id: str, version: str | None, query: FileQuery, needle: str
) -> Iterator[FileItem]:
    # PostgreSQL JSON extraction also rejects escaped NUL in other fields of an object.
    # Decode the original JSON for unsafe filters or a conservatively marked legacy home.
    table, column = ("versions", "manifest") if version else ("datasets", "files")
    statement = text(f"SELECT {column} FROM {table} WHERE id = :id")  # noqa: S608
    raw = session.scalar(statement, {"id": version or dataset_id})
    values = json.loads(raw) if isinstance(raw, str) else raw
    items = (FileItem.model_validate(value) for value in values)
    for batch in batched(items, 100):
        for item in overlay_files(session, dataset_id, list(batch)):
            if (query.modality is None or item.modality == query.modality) and (
                not needle or needle in unicodedata.normalize("NFC", item.filename).casefold()
            ):
                yield item


def _sql_rows(
    session: Session, dataset_id: str, version: str | None, query: FileQuery
) -> Iterator[FileItem]:
    """Stream candidates, keeping Unicode normalization before filtering and pagination."""
    sqlite = session.get_bind().dialect.name == "sqlite"
    needle = unicodedata.normalize("NFC", query.q).casefold()
    sql_needle = needle if needle.isascii() else ""
    escaped = sql_needle.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    parameters = {
        "dataset": dataset_id,
        "id": version or dataset_id,
        "modality": query.modality,
        "q": sql_needle,
        "pattern": f"%{escaped}%",
        "limit": (-1 if sqlite else None) if needle else query.limit or (-1 if sqlite else None),
        "offset": 0 if needle else query.offset,
    }
    statement = text(_statement(sqlite=sqlite, version=bool(version)))
    with session.execute(statement.execution_options(yield_per=100), parameters) as rows:
        for row in rows:
            value = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            item = FileItem.model_validate(value)
            modality_matches = query.modality is None or item.modality == query.modality
            if modality_matches and (
                not needle or needle in unicodedata.normalize("NFC", item.filename).casefold()
            ):
                yield item


def read_file_page(
    session: Session, dataset_id: str, version: str | None, query: FileQuery
) -> list[FileItem]:
    """Overlay only the selected page, applying literal Unicode filters before slicing."""
    snapshot = begin_file_read(session)
    _require_manifest(session, dataset_id, version)
    fallback = not snapshot or _python_filter(query) or requires_python_files(session)
    items = (
        _fallback_rows(
            session, dataset_id, version, query, unicodedata.normalize("NFC", query.q).casefold()
        )
        if fallback
        else _sql_rows(session, dataset_id, version, query)
    )
    if query.q or fallback:
        items = islice(items, query.offset, query.offset + query.limit if query.limit else None)
    return overlay_files(session, dataset_id, list(items))
