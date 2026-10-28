# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read CSV or optional Parquet into an immutable string-valued table."""

from __future__ import annotations

import csv
import importlib
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from pydantic import ValidationError as ModelValidationError
from pydantic import model_validator

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem, Record
from datakeel.operators.base import artifact

if TYPE_CHECKING:
    from collections.abc import Sequence


class TableData(Record):
    """Keep table values and original one-based source row coordinates together."""

    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    row_numbers: tuple[int, ...]

    @model_validator(mode="after")
    def validate_shape(self) -> TableData:
        """Reject ambiguous headers, ragged rows and invalid source coordinates."""
        if len(set(self.columns)) != len(self.columns) or any(not name for name in self.columns):
            msg = "Table column names must be nonempty and unique"
            raise ValidationError(msg)
        if len(self.rows) != len(self.row_numbers) or any(
            len(row) != len(self.columns) for row in self.rows
        ):
            msg = "Table rows, columns and source row numbers must have matching shapes"
            raise ValidationError(msg)
        if any(number < 1 for number in self.row_numbers):
            msg = "Table source row numbers must be positive"
            raise ValidationError(msg)
        return self


class _ArrowTable(Protocol):
    column_names: Sequence[str]

    def to_pylist(self) -> list[dict[str, object]]: ...


class _ParquetReader(Protocol):
    def read_table(self, source: str) -> _ArrowTable: ...


def _csv_table(path: Path, delimiter: str) -> TableData:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        columns = tuple(next(reader, ()))
        rows: list[tuple[str, ...]] = []
        row_numbers: list[int] = []
        previous_line = reader.line_num
        for row in reader:
            if row:
                rows.append(tuple(row))
                row_numbers.append(previous_line + 1)
            previous_line = reader.line_num
    return TableData(columns=columns, rows=tuple(rows), row_numbers=tuple(row_numbers))


def _parquet_table(path: Path) -> TableData:
    try:
        reader = cast("_ParquetReader", importlib.import_module("pyarrow.parquet"))
    except ImportError as exc:
        msg = "Parquet requires user-installed pyarrow; install it with: pip install pyarrow"
        raise ValidationError(msg) from exc
    table = reader.read_table(str(path))
    columns = tuple(table.column_names)
    rows = tuple(
        tuple("" if record[name] is None else str(record[name]) for name in columns)
        for record in table.to_pylist()
    )
    return TableData(columns=columns, rows=rows, row_numbers=tuple(range(2, len(rows) + 2)))


def _source_rows(file: FileItem, table: TableData) -> TableData:
    source: object = file.metadata.get("source_row_numbers")
    if source is None:
        return table
    if not isinstance(source, list):
        msg = "source_row_numbers must be a list of positive integers"
        raise ValidationError(msg)
    coordinates = cast("list[object]", source)
    if len(coordinates) != len(table.rows) or any(
        type(value) is not int or value < 1 for value in coordinates
    ):
        msg = "source_row_numbers must contain one positive integer per table row"
        raise ValidationError(msg)
    return TableData(
        columns=table.columns,
        rows=table.rows,
        row_numbers=tuple(cast("list[int]", coordinates)),
    )


def read_table(file: FileItem) -> TableData:
    """Read UTF-8 CSV or lazily load the user's optional Parquet implementation."""
    path = Path(file.path)
    extension = Path(file.filename).suffix.lower()
    try:
        if extension in {".csv", ".tsv"}:
            table = _csv_table(path, "\t" if extension == ".tsv" else ",")
        elif extension in {".parquet", ".pq"}:
            table = _parquet_table(path)
        else:
            msg = "Table operators support .csv, .tsv and .parquet files"
            raise ValidationError(msg)
    except (OSError, UnicodeError, csv.Error) as exc:
        msg = f"Unable to read table: {type(exc).__name__}"
        raise ValidationError(msg) from exc
    except ModelValidationError as exc:
        msg = "Invalid table shape or header; columns must be unique and rows must match the header"
        raise ValidationError(msg) from exc
    return _source_rows(file, table)


def write_table(file: FileItem, output_dir: Path, data: TableData) -> FileItem:
    """Write stable CSV bytes while preserving metadata and source row provenance."""
    checked = TableData.model_validate(data.model_dump())
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(checked.columns)
    writer.writerows(checked.rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    original_source: object = file.metadata.get("original_source_file_id")
    return artifact(
        file,
        output_dir,
        stream.getvalue().encode("utf-8"),
        "csv",
        original_source_file_id=original_source if isinstance(original_source, str) else file.id,
        source_row_numbers=list(checked.row_numbers),
    )
