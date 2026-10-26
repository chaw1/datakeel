# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Discover current local objects from existing facts without maintaining an index."""

import unicodedata
from itertools import zip_longest
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogObject
from datakeel.core.models import FileItem
from datakeel.core.search_models import SEARCH_KINDS, SearchKind, SearchQuery, SearchResult
from datakeel.storage.action_rows import ActionRunRow
from datakeel.storage.catalog_rows import CatalogObjectRow
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.file_state import FileStateRow


def _files(session: Session, versions: list[VersionRow]) -> list[SearchResult]:
    states = {row.file_id: row for row in session.scalars(select(FileStateRow))}
    files: dict[str, SearchResult] = {}
    for version in versions:
        for raw in version.manifest:
            file = FileItem.model_validate(raw)
            state = states.get(file.id)
            status = (
                "deleted"
                if state and state.deleted
                else "quarantined"
                if state and state.quarantined
                else "normal"
            )
            files.setdefault(
                file.id,
                SearchResult(
                    kind="file",
                    id=file.id,
                    name=file.filename,
                    dataset_id=version.dataset_id,
                    version_id=version.id,
                    status=status,
                ),
            )
    return list(files.values())


def _datasets(session: Session) -> list[SearchResult]:
    datasets = list(session.scalars(select(DatasetRow).order_by(DatasetRow.id)))
    versions = list(
        session.scalars(select(VersionRow).order_by(VersionRow.created_at, VersionRow.id))
    )
    counts: dict[str, int] = {}
    names = {row.id: row.name for row in datasets}
    result = _files(session, versions)
    for version in versions:
        counts[version.dataset_id] = counts.get(version.dataset_id, 0) + 1
        result.append(
            SearchResult(
                kind="version",
                id=version.id,
                name=f"{names[version.dataset_id]} · v{counts[version.dataset_id]}",
                dataset_id=version.dataset_id,
                version_id=version.id,
                status="immutable",
            )
        )
    result.extend(
        SearchResult(
            kind="dataset",
            id=row.id,
            name=row.name,
            dataset_id=row.id,
            status="versioned" if row.id in counts else "empty",
        )
        for row in datasets
    )
    return result


def _catalog(session: Session) -> list[SearchResult]:
    result: list[SearchResult] = []
    for row in session.scalars(
        select(CatalogObjectRow).where(
            CatalogObjectRow.kind.in_(["table", "column", "metric", "term"])
        )
    ):
        item = CatalogObject.model_validate(row.payload)
        result.append(
            SearchResult(
                kind=cast("SearchKind", row.kind),
                id=row.asset_id,
                name=item.name,
                english_name=item.english_name,
            )
        )
    return result


def _rank(item: SearchResult, query: str) -> tuple[int, str, str, str]:
    identity, name = item.id.casefold(), unicodedata.normalize("NFC", item.name).casefold()
    names = (name, unicodedata.normalize("NFC", item.english_name or "").casefold())
    rank = (
        0
        if identity == query
        else 1
        if identity.startswith(query)
        else 2
        if query in names
        else 3
        if any(value.startswith(query) for value in names)
        else 4
    )
    return rank, name, item.kind, item.id


def search_objects(db: Database, query: SearchQuery) -> list[SearchResult]:
    """Search eight object kinds, prioritizing exact identities and unique ID prefixes."""
    with db.session() as session:
        items = _datasets(session) + _catalog(session)
        items.extend(
            SearchResult(
                kind="action_run",
                id=row.id,
                name=row.action_type,
                status=row.status,
            )
            for row in session.scalars(select(ActionRunRow))
        )
    needle = unicodedata.normalize("NFC", query.q).strip().casefold()
    if needle:
        matches = [
            item
            for item in items
            if needle in item.id.casefold()
            or needle in unicodedata.normalize("NFC", item.name).casefold()
            or needle in unicodedata.normalize("NFC", item.english_name or "").casefold()
        ]
        return sorted(matches, key=lambda item: _rank(item, needle))[: query.limit]
    groups = [
        sorted(
            (item for item in items if item.kind == kind),
            key=lambda item: (item.name.casefold(), item.id),
        )
        for kind in SEARCH_KINDS
    ]
    return [item for row in zip_longest(*groups) for item in row if item is not None][: query.limit]
