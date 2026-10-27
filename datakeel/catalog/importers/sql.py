# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Derive column relationships from SQL syntax and qualified sqlglot lineage."""

from itertools import pairwise

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.lineage import Node, lineage  # pyright: ignore[reportUnknownVariableType]  # Untyped schema dict in dependency.
from sqlglot.tokenizer_core import TokenType

from datakeel.catalog.importers.helpers import contains, metadata_object
from datakeel.catalog.importers.models import SqlDefinition
from datakeel.core.catalog_identity import catalog_id, catalog_segments
from datakeel.core.catalog_models import (
    CatalogLink,
    CatalogObject,
    CatalogSnapshot,
    ColumnProperties,
    SqlFailure,
    TableProperties,
)
from datakeel.core.models import BoundaryModel


class LineageBatch(BoundaryModel):
    """Return metadata enriched by parsed SQL and explicit failures."""

    snapshot: CatalogSnapshot
    failures: tuple[SqlFailure, ...]


def _schema(snapshot: CatalogSnapshot) -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {}
    for item in snapshot.objects:
        if item.asset_ref.asset_type == "column" and item.table_id and item.schema_name:
            table = catalog_segments(item.table_id)[-1]
            result.setdefault(item.schema_name, {}).setdefault(table, {})[item.name] = (
                ColumnProperties.model_validate(
                    {
                        key: value
                        for key, value in item.properties.root.items()
                        if key in ColumnProperties.model_fields
                    }
                ).data_type
            )
    return result


def _query(definition: SqlDefinition) -> tuple[str, exp.Query]:
    expression = sqlglot.parse_one(definition.sql, read=definition.dialect)
    table_id = definition.table_id
    if isinstance(expression, exp.Create):
        target = expression.this
        if isinstance(target, exp.Table):
            source_id, schema, _name = catalog_segments(table_id)
            table_id = catalog_id(source_id, target.db or schema, target.name)
        expression = expression.expression
    if not isinstance(expression, exp.Query):
        msg = "Field lineage requires a SELECT query or CREATE VIEW/TABLE AS SELECT"
        raise SqlglotError(msg)
    return table_id, expression


def _existing_column(snapshot: CatalogSnapshot, identity: str) -> CatalogObject | None:
    parts = catalog_segments(identity)
    columns = tuple(item for item in snapshot.objects if item.asset_ref.asset_type == "column")
    exact = next(
        (item for item in columns if catalog_segments(item.asset_ref.asset_id) == parts), None
    )
    if exact:
        return exact
    folded = tuple(part.casefold() for part in parts)
    matches = [
        item
        for item in columns
        if tuple(part.casefold() for part in catalog_segments(item.asset_ref.asset_id)) == folded
    ]
    return matches[0] if len(matches) == 1 else None


def _leaves(root: Node, table_id: str, snapshot: CatalogSnapshot) -> set[str]:
    source_id, schema, _name = catalog_segments(table_id)
    result: set[str] = set()
    for node in root.walk():
        if node.downstream or not isinstance(node.expression, exp.Table):
            continue
        table = node.expression
        column = node.name.rsplit(".", 1)[-1].strip('"`')
        identity = catalog_id(source_id, table.db or schema, table.name, column)
        existing = _existing_column(snapshot, identity)
        if existing is None:
            msg = f"SQL references an unregistered field: {identity}"
            raise SqlglotError(msg)
        result.add(existing.asset_ref.asset_id)
    return result


def _output_name(output: str, names: tuple[str, ...]) -> str:
    if output in names:
        return output
    matches = [name for name in names if name.casefold() == output.casefold()]
    return matches[0] if len(matches) == 1 else output


def _derive(definition: SqlDefinition, snapshot: CatalogSnapshot) -> CatalogSnapshot:
    table_id, query = _query(definition)
    _source, schema, table_name = catalog_segments(table_id)
    parsed = lineage(None, query, schema=_schema(snapshot), dialect=definition.dialect, db=schema)
    roots = parsed
    objects = {item.asset_ref.asset_id: item for item in snapshot.objects}
    source = objects[table_id.split("/")[0]]
    table = objects.get(table_id) or metadata_object(
        "table", table_id, table_name, TableProperties(is_view=True, sql=definition.sql)
    )
    additions: list[CatalogObject] = [] if table_id in objects else [table]
    links: list[CatalogLink] = [] if table_id in objects else [contains(source, table)]
    original_names = tuple(query.named_selects)
    for index, (output, root) in enumerate(roots.items()):
        column = _output_name(output, original_names)
        target_id = catalog_id(*catalog_segments(table_id), column)
        target = _existing_column(snapshot, target_id) or metadata_object(
            "column", target_id, column, ColumnProperties(data_type="UNKNOWN", ordinal=index)
        )
        if target.asset_ref.asset_id not in objects:
            additions.append(target)
            links.append(contains(table, target))
        links.extend(
            CatalogLink(source=objects[identity].asset_ref, target=target.asset_ref, kind="derived")
            for identity in sorted(_leaves(root, table_id, snapshot))
        )
    return snapshot.model_copy(
        update={
            "objects": snapshot.objects + tuple(additions),
            "links": snapshot.links + tuple(links),
        }
    )


def _statements(definition: SqlDefinition) -> list[str]:
    tokens = sqlglot.tokenize(definition.sql, read=definition.dialect)
    if not tokens:
        return []
    boundaries = [
        -1,
        *(token.start for token in tokens if token.token_type == TokenType.SEMICOLON),
        len(definition.sql),
    ]
    return [
        definition.sql[start + 1 : end]
        for start, end in pairwise(boundaries)
        if definition.sql[start + 1 : end].strip()
    ]


def derive_sql(snapshot: CatalogSnapshot, definitions: tuple[SqlDefinition, ...]) -> LineageBatch:
    """Parse each view or SQL statement; retain valid lineage while reporting failures."""
    failures: list[SqlFailure] = []
    for definition in definitions:
        try:
            statements = _statements(definition)
        except SqlglotError as error:
            failures.append(SqlFailure(origin=definition.origin, reason=str(error)))
            continue
        for index, statement in enumerate(statements, 1):
            try:
                snapshot = _derive(
                    definition.model_copy(update={"sql": statement}),
                    snapshot,
                )
            except (SqlglotError, ValueError) as error:
                failures.append(
                    SqlFailure(origin=f"{definition.origin}#{index}", reason=str(error))
                )
    unique = {
        (link.kind, link.source.asset_id, link.target.asset_id): link for link in snapshot.links
    }
    snapshot = snapshot.model_copy(update={"links": tuple(unique[key] for key in sorted(unique))})
    return LineageBatch(snapshot=snapshot, failures=tuple(failures))
