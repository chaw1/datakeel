# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project one frozen source document without loading or parsing an entire execution run."""

from sqlalchemy import JSON, case, func, select, true, type_coerce

from datakeel.core.kg_execution import KGDocument
from datakeel.core.kg_queries import KGSourceText
from datakeel.storage.database import Database
from datakeel.storage.kg_rows import KGRunRow


def frozen_text_source(
    db: Database, extraction_id: str, asset_id: str, version_id: str
) -> KGSourceText | None:
    """Read exact source text from current or legacy documents using a narrow SQL projection."""
    with db.session() as session:
        expand = (
            func.json_each
            if session.get_bind().dialect.name == "sqlite"
            else func.json_array_elements
        )
        sources = case(
            (
                KGRunRow.payload["documents"].as_string().is_(None),
                KGRunRow.payload["prepared"]["documents"],
            ),
            else_=KGRunRow.payload["documents"],
        )
        documents = expand(sources).table_valued("value")
        document = type_coerce(documents.c.value, JSON)
        statement = (
            select(document)
            .select_from(KGRunRow)
            .join(documents, true())
            .where(
                KGRunRow.id == extraction_id,
                document["asset_ref"]["asset_id"].as_string() == asset_id,
                document["asset_ref"]["version"].as_string() == version_id,
            )
            .limit(1)
        )
        payload = session.scalar(statement)
    if payload is None:
        return None
    source = KGDocument.model_validate(payload)
    return KGSourceText(asset_ref=source.asset_ref, filename=source.filename, text=source.text)
