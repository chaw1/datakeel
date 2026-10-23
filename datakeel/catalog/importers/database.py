# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only SQLAlchemy reflection for the P4 SQLite source adapter."""

from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import SQLAlchemyError

from datakeel.catalog.importers.helpers import contains, metadata_object
from datakeel.catalog.importers.models import ImportBatch, SqlDefinition
from datakeel.core.catalog_identity import catalog_id, catalog_segments
from datakeel.core.catalog_models import (
    CatalogImportRequest,
    CatalogLink,
    CatalogObject,
    CatalogSnapshot,
    ColumnProperties,
    ForeignKey,
    SourceProperties,
    TableProperties,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import AssetRef


def _connection_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        msg = "P4 catalog reflection supports only SQLite sources"
        raise ValidationError(msg)
    if parsed.database is not None and parsed.database != ":memory:":
        path = Path(parsed.database).resolve()
        if not path.is_file():
            msg = f"SQLite source does not exist: {path}"
            raise ValidationError(msg)
        return f"sqlite:///file:{path}?mode=ro&uri=true"
    return url


def _comment(inspector: Inspector, table: str, schema: str) -> str | None:
    try:
        return inspector.get_table_comment(table, schema).get("text")
    except NotImplementedError:
        return None


def _table(
    inspector: Inspector, source: CatalogObject, schema: str, name: str, *, is_view: bool
) -> tuple[CatalogObject, list[CatalogObject], list[CatalogLink]]:
    source_name = catalog_segments(source.asset_ref.asset_id)[0]
    table_id = catalog_id(source_name, schema, name)
    reflected = inspector.get_columns(name, schema)
    primary = tuple(inspector.get_pk_constraint(name, schema).get("constrained_columns") or ())
    foreign = tuple(
        ForeignKey(
            columns=tuple(key["constrained_columns"]),
            target_table=catalog_id(
                source_name, key.get("referred_schema") or schema, key["referred_table"]
            ),
            target_columns=tuple(key["referred_columns"]),
        )
        for key in inspector.get_foreign_keys(name, schema)
    )
    properties = TableProperties(
        columns={column["name"]: str(column["type"]) for column in reflected},
        is_view=is_view,
        comment=_comment(inspector, name, schema),
        primary_key=primary,
        foreign_keys=foreign,
        sql=inspector.get_view_definition(name, schema) if is_view else None,
    )
    table = metadata_object("table", table_id, name, properties)
    columns = [
        metadata_object(
            "column",
            catalog_id(source_name, schema, name, column["name"]),
            column["name"],
            ColumnProperties(
                data_type=str(column["type"]),
                nullable=column["nullable"],
                primary_key=column["name"] in primary,
                comment=column.get("comment"),
                ordinal=index,
            ),
        )
        for index, column in enumerate(reflected)
    ]
    relations = [contains(source, table), *(contains(table, column) for column in columns)]
    by_name = {column.name: column for column in columns}
    for key in foreign:
        for local, target in zip(key.columns, key.target_columns, strict=True):
            target_id = catalog_id(*catalog_segments(key.target_table), target)
            relations.append(
                CatalogLink(
                    source=by_name[local].asset_ref,
                    target=AssetRef(asset_type="column", asset_id=target_id, display_name=target),
                    kind="references",
                )
            )
    return table, columns, relations


def _reflect(inspector: Inspector, request: CatalogImportRequest) -> ImportBatch:
    dialect = inspector.bind.dialect.name
    source = metadata_object(
        "source",
        catalog_id(request.source_id),
        request.name,
        SourceProperties(connection_url=request.connection_url, dialect=dialect),
    )
    objects = [source]
    links: list[CatalogLink] = []
    definitions: list[SqlDefinition] = []
    schemas = request.schemas or tuple(
        name
        for name in inspector.get_schema_names()
        if name not in {"information_schema", "pg_catalog"}
    )
    for schema in schemas:
        views = set(inspector.get_view_names(schema))
        for name in sorted(set(inspector.get_table_names(schema)) | views):
            table, columns, relations = _table(
                inspector, source, schema, name, is_view=name in views
            )
            objects.extend([table, *columns])
            links.extend(relations)
            sql = TableProperties.model_validate(table.properties.root).sql
            if sql:
                definitions.append(
                    SqlDefinition(
                        origin=table.asset_ref.asset_id,
                        table_id=table.asset_ref.asset_id,
                        sql=sql,
                        dialect=dialect,
                    )
                )
    return ImportBatch(
        snapshot=CatalogSnapshot(
            scope=f"source:{request.source_id}", objects=tuple(objects), links=tuple(links)
        ),
        sql=tuple(definitions),
    )


def reflect_database(request: CatalogImportRequest) -> ImportBatch:
    """Reflect table, column, key, comment, and view metadata without modifying its source."""
    if not request.connection_url:
        msg = "Database reflection requires connection_url"
        raise ValidationError(msg)
    engine = create_engine(_connection_url(request.connection_url))
    try:
        with engine.connect() as connection:
            return _reflect(inspect(connection), request)
    except SQLAlchemyError as error:
        msg = f"Source reflection failed: {type(error).__name__}"
        raise ValidationError(msg) from error
    finally:
        engine.dispose()
