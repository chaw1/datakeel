# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise CSV fidelity, original-row provenance and optional Parquet loading."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from datakeel.operators.table import io
from datakeel.operators.table.io import TableData, read_table, write_table

if TYPE_CHECKING:
    from tests.operators.factories import FileFactory


def test_csv_quotes_bom_blank_lines_preserve_original_coordinates(make_file: FileFactory) -> None:
    """A quoted newline counts as two physical lines and empty records are skipped."""
    file = make_file(
        '\ufeffid,note\r\n1,"first\nsecond"\r\n\r\n2,"comma, quote"\r\n', "data.csv", "table"
    )
    assert read_table(file) == TableData(
        columns=("id", "note"),
        rows=(("1", "first\nsecond"), ("2", "comma, quote")),
        row_numbers=(2, 5),
    )


def test_csv_write_preserves_metadata_and_reordered_source_rows(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Reading a derived CSV retains coordinates from the original source."""
    source = make_file("id,value\n1,alpha\n2,beta\n", "data.csv", "table")
    source.metadata["custom"] = {"key": "kept"}
    data = TableData(
        columns=("id", "value"), rows=(("2", "beta"), ("1", "alpha")), row_numbers=(3, 2)
    )
    output = write_table(source, output_dir, data)
    assert read_table(output) == data
    assert output.metadata["custom"] == {"key": "kept"}
    assert output.metadata["source_file_id"] == source.id
    assert output.filename == "data.csv"
    assert Path(output.path).read_bytes() == b"id,value\n2,beta\n1,alpha\n"
    assert Path(source.path).read_bytes() == b"id,value\n1,alpha\n2,beta\n"


def test_tsv_support_does_not_split_embedded_commas(make_file: FileFactory) -> None:
    """TSV uses its declared separator rather than guessing from values."""
    file = make_file("id\tnote\n1\tvalue, with comma\n", "data.tsv", "table")
    assert read_table(file).rows == (("1", "value, with comma"),)


@pytest.mark.parametrize("inherited", [None, 17, "already-original"])
def test_second_write_keeps_original_file_identity_and_source_row_coordinates(
    inherited: object, make_file: FileFactory, output_dir: Path
) -> None:
    """Repeated normalization and ordering retain the first file's evidence identity."""
    source = make_file("id,value\nA,1\nB,2\n", "source.csv", "table")
    source.metadata["original_source_file_id"] = inherited
    data = read_table(source)
    first = write_table(source, output_dir / "first", data)
    reordered = data.model_copy(update={"rows": data.rows[::-1], "row_numbers": (3, 2)})
    second = write_table(first, output_dir / "second", reordered)
    expected = inherited if isinstance(inherited, str) else source.id
    assert first.metadata["original_source_file_id"] == expected
    assert second.metadata["original_source_file_id"] == expected
    assert second.metadata["source_file_id"] == first.id
    assert read_table(second).row_numbers == (3, 2)


@pytest.mark.parametrize(
    "content",
    ["id,id\n1,2\n", "id,\n1,2\n", "id,value\n1\n", 'id,value\n1,"unfinished\n'],
)
def test_malformed_csv_rejected_without_silent_data_loss(
    content: str, make_file: FileFactory
) -> None:
    """Duplicate headers, missing headers, ragged rows and invalid quotes fail."""
    with pytest.raises(ValidationError):
        read_table(make_file(content, "data.csv", "table"))


@pytest.mark.parametrize("coordinates", [[2], [2, False], [0, 3], "2,3"])
def test_invalid_row_provenance_is_rejected(coordinates: object, make_file: FileFactory) -> None:
    """A malformed provenance mapping must never shift evidence to another row."""
    file = make_file("id\n1\n2\n", "data.csv", "table")
    file.metadata["source_row_numbers"] = coordinates
    with pytest.raises(ValidationError, match="source_row_numbers"):
        read_table(file)


def test_parquet_is_loaded_lazily_with_actionable_missing_dependency(
    make_file: FileFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CSV works without loading Parquet, while Parquet reports an install hint."""
    imports: list[str] = []

    def missing(name: str) -> object:
        imports.append(name)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(io.importlib, "import_module", missing)
    read_table(make_file("id\n1\n", "data.csv", "table"))
    assert imports == []
    with pytest.raises(ValidationError, match="pip install pyarrow"):
        read_table(make_file(b"not-parquet", "data.parquet", "table"))
    assert imports == ["pyarrow.parquet"]


class _FakeArrowTable:
    column_names = ("id", "value", "enabled")

    def to_pylist(self) -> list[dict[str, object]]:
        return [{"id": 1, "value": None, "enabled": True}]


class _FakeParquetReader:
    def read_table(self, source: str) -> _FakeArrowTable:
        assert source.endswith("data.parquet")
        return _FakeArrowTable()


def test_parquet_adapter_returns_typed_string_values(
    make_file: FileFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The optional adapter handles nulls without passing library objects onward."""
    monkeypatch.setattr(io.importlib, "import_module", lambda _: _FakeParquetReader())
    table = read_table(make_file(b"fake", "data.parquet", "table"))
    assert table == TableData(
        columns=("id", "value", "enabled"), rows=(("1", "", "True"),), row_numbers=(2,)
    )


def test_unsupported_format_is_explicit(make_file: FileFactory) -> None:
    """Spreadsheet binaries are not accidentally decoded as CSV."""
    with pytest.raises(ValidationError, match="support"):
        read_table(make_file(b"", "data.xlsx", "table"))


def test_unreadable_and_non_utf8_tables_raise_domain_failures(make_file: FileFactory) -> None:
    """Filesystem and encoding problems cross the reader boundary predictably."""
    file = make_file(b"\xff\xfe", "data.csv", "table")
    with pytest.raises(ValidationError, match="Unable to read"):
        read_table(file)
    Path(file.path).unlink()
    with pytest.raises(ValidationError, match="Unable to read"):
        read_table(file)
