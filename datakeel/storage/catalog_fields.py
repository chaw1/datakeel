# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read narrow catalog navigation fields with exact fallback for escaped legacy JSON."""

from collections.abc import Iterator

from sqlalchemy import Select, String, case, cast, func, or_
from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogObject
from datakeel.core.models import BoundaryModel
from datakeel.storage.catalog_rows import CatalogObjectRow


class CatalogFields(BoundaryModel):
    """Retain only the typed public fields needed by paging and discovery."""

    identity: str
    kind: str
    name: str
    english_name: str | None
    source_id: str | None


def read_fields(session: Session, statement: Select[CatalogObjectRow]) -> Iterator[CatalogFields]:
    """Project ordinary JSON fields and decode only escaped legacy payloads in Python."""
    value = cast(CatalogObjectRow.payload, String)
    unsafe = (
        or_(
            func.lower(value).op("GLOB")(r"*\u0000*"),
            func.lower(value).op("GLOB")(r"*\ud[89abcdef]*"),
        )
        if session.get_bind().dialect.name == "sqlite"
        else value.op("~")(r"\\u(0000|[dD][89a-fA-F])")
    )
    # CASE prevents JSON text extraction from inspecting an unsafe object's other fields.
    projected = statement.with_only_columns(
        CatalogObjectRow.asset_id,
        CatalogObjectRow.kind,
        case((unsafe, None), else_=CatalogObjectRow.payload["name"].as_string()),
        case((unsafe, None), else_=CatalogObjectRow.payload["english_name"].as_string()),
        case((unsafe, None), else_=CatalogObjectRow.payload["source_id"].as_string()),
        case((unsafe, CatalogObjectRow.payload)),
    )
    for identity, kind, name, english, source, raw in session.execute(
        projected.execution_options(yield_per=1000)
    ):
        item = CatalogObject.model_validate(raw) if raw is not None else None
        yield CatalogFields(
            identity=identity,
            kind=kind,
            name=item.name if item else name,
            english_name=item.english_name if item else english,
            source_id=item.source_id if item else source,
        )
