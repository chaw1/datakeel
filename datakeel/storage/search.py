# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Discover public objects with bounded result retention and exact Unicode ranking."""

import heapq
import unicodedata
from collections.abc import Iterator
from itertools import chain, zip_longest

from sqlalchemy.orm import Session

from datakeel.core.search_models import SEARCH_KINDS, SearchQuery, SearchResult
from datakeel.storage.database import Database
from datakeel.storage.file_discovery import begin_file_read
from datakeel.storage.search_sources import dataset_results, file_results, other_results


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


def _all(session: Session, query: SearchQuery) -> Iterator[SearchResult]:
    return chain(dataset_results(session), file_results(session, query), other_results(session))


def _matches(item: SearchResult, needle: str) -> bool:
    return (
        needle in item.id.casefold()
        or needle in unicodedata.normalize("NFC", item.name).casefold()
        or needle in unicodedata.normalize("NFC", item.english_name or "").casefold()
    )


def _initial(session: Session, limit: int) -> list[SearchResult]:
    groups: dict[str, list[SearchResult]] = {kind: [] for kind in SEARCH_KINDS}
    for item in _all(session, SearchQuery(limit=limit)):
        values = groups[item.kind]
        values.append(item)
        if len(values) > limit:
            values.sort(key=lambda value: (value.name.casefold(), value.id))
            values.pop()
    ordered = [
        sorted(groups[kind], key=lambda value: (value.name.casefold(), value.id))
        for kind in SEARCH_KINDS
    ]
    return [item for row in zip_longest(*ordered) for item in row if item is not None][:limit]


def search_objects(db: Database, query: SearchQuery) -> list[SearchResult]:
    """Search public fields without loading all original manifest or catalog payloads."""
    needle = unicodedata.normalize("NFC", query.q).strip().casefold()
    with db.session() as session:
        begin_file_read(session)
        if not needle:
            return _initial(session, query.limit)
        return heapq.nsmallest(
            query.limit,
            (
                item
                for item in _all(session, SearchQuery(q=needle, limit=query.limit))
                if _matches(item, needle)
            ),
            key=lambda item: _rank(item, needle),
        )
