# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Infer local table metadata for the existing controlled catalog import action."""

from pathlib import Path

from datakeel.catalog.importers.helpers import contains, metadata_object
from datakeel.catalog.importers.models import ImportBatch
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import (
    CatalogImportRequest,
    CatalogLink,
    CatalogObject,
    CatalogSnapshot,
    ColumnProperties,
    SourceProperties,
    TableProperties,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem, JsonDocument
from datakeel.operators.table.models import TableProfile
from datakeel.operators.table.profile import ProfileParams, execute


def _table(
    request: CatalogImportRequest, path: Path, profile: TableProfile
) -> tuple[CatalogObject, ...]:
    table_id = catalog_id(request.source_id, "main", path.stem)
    table = metadata_object(
        "table",
        table_id,
        path.stem,
        TableProperties(
            columns={column.name: column.inferred_type for column in profile.columns},
            table_profile=JsonDocument.model_validate(profile.model_dump(mode="json")),
        ),
    )
    columns = tuple(
        metadata_object(
            "column",
            catalog_id(request.source_id, "main", path.stem, column.name),
            column.name,
            ColumnProperties(
                data_type=column.inferred_type,
                nullable=column.null_count > 0,
                ordinal=index,
                profile=JsonDocument.model_validate(column.model_dump(mode="json")),
            ),
        )
        for index, column in enumerate(profile.columns)
    )
    return table, *columns


def reflect_files(request: CatalogImportRequest) -> ImportBatch:
    """Freeze inferred CSV, TSV, or optionally Parquet profiles without publishing facts."""
    if not request.files or request.connection_url:
        msg = "File catalog import requires files without a connection_url"
        raise ValidationError(msg)
    if request.sql_files or request.schemas:
        msg = "File catalog import does not accept SQL files or schema selection"
        raise ValidationError(msg)
    paths = sorted((Path(value) for value in request.files), key=lambda path: path.name)
    if len({path.stem for path in paths}) != len(paths):
        msg = "File catalog import requires unique table names (filename stems)"
        raise ValidationError(msg)
    source = metadata_object(
        "source",
        catalog_id(request.source_id),
        request.name,
        SourceProperties(dialect="file", files=tuple(path.name for path in paths)),
    )
    objects = [source]
    links: list[CatalogLink] = []
    files = [FileItem(path=str(path), filename=path.name, modality="table") for path in paths]
    result = execute(files, Path(), ProfileParams())
    for path, file in zip(paths, result.files, strict=True):
        profile = TableProfile.model_validate(file.metadata["table_profile"])
        table, *columns = _table(request, path, profile)
        objects.extend((table, *columns))
        links.extend((contains(source, table), *(contains(table, column) for column in columns)))
    return ImportBatch(
        snapshot=CatalogSnapshot(
            scope=f"source:{request.source_id}", objects=tuple(objects), links=tuple(links)
        )
    )
