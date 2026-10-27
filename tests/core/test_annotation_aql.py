# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independently transcribed standard-table values and arrow/full-inspection boundaries."""

import pytest

from datakeel.core.annotation_aql import load_aql_table, lookup_aql
from datakeel.core.errors import ValidationError


@pytest.mark.parametrize(
    ("lot", "aql", "code", "effective", "count", "acceptance"),
    [
        (8, 2.5, "A", "C", 5, 0),
        (15, 4.0, "B", "B", 3, 0),
        (25, 4.0, "C", "B", 3, 0),
        (50, 4.0, "D", "E", 13, 1),
        (90, 1.5, "E", "D", 8, 0),
        (150, 2.5, "F", "F", 20, 1),
        (280, 1.5, "G", "G", 32, 1),
        (500, 1.0, "H", "H", 50, 1),
        (1200, 2.5, "J", "J", 80, 5),
        (3200, 4.0, "K", "K", 125, 10),
        (10000, 6.5, "L", "L", 200, 21),
        (35000, 2.5, "M", "M", 315, 14),
        (150000, 2.5, "N", "N", 500, 21),
        (500000, 2.5, "P", "N", 500, 21),
        (500001, 6.5, "Q", "L", 200, 21),
        (20, 0.65, "C", "F", 20, 0),
        (2, 1.0, "A", "E", 2, 0),
    ],
)
def test_aql_lookup_matches_published_tables(
    lot: int, aql: float, code: str, effective: str, count: int, acceptance: int
) -> None:
    """MIL-STD-105E 1989 Table I p13 and Table II-A p14; arrows use target plan size."""
    result = lookup_aql(lot, aql)
    assert (
        result.code_letter,
        result.effective_code_letter,
        result.sample_size,
        result.acceptance_number,
        result.rejection_number,
    ) == (code, effective, count, acceptance, acceptance + 1)


@pytest.mark.parametrize(
    ("lot", "aql", "code", "effective", "count", "acceptance"),
    [
        (300, 0.65, "H", "J", 80, 1),
        (60, 2.5, "E", "F", 20, 1),
        (200, 1.0, "G", "H", 50, 1),
        (100, 1.5, "F", "G", 32, 1),
        (12, 6.5, "B", "A", 2, 0),
        (20, 6.5, "C", "D", 8, 1),
        (1000, 0.4, "J", "K", 125, 1),
        (1000, 0.25, "J", "H", 50, 0),
        (5000, 0.1, "L", "K", 125, 0),
        (20000, 0.1, "M", "N", 500, 1),
        (200000, 0.015, "P", "P", 800, 0),
        (600000, 0.015, "Q", "P", 800, 0),
        (600000, 0.01, "Q", "Q", 1250, 0),
        (600000, 0.025, "Q", "R", 2000, 1),
        (600000, 1.0, "Q", "Q", 1250, 21),
        (40, 10, "D", "D", 8, 2),
        (2000, 10, "K", "K", 125, 21),
        (5000, 10, "L", "K", 125, 21),
        (5, 10, "A", "C", 5, 1),
        (500, 0.01, "H", "Q", 500, 0),
    ],
)
def test_aql_arrow_cells_follow_the_scanned_master_table(
    lot: int, aql: float, code: str, effective: str, count: int, acceptance: int
) -> None:
    """MIL-STD-105E Table II-A p14, read cell by cell: after Ac=0 a column has up then down.

    Same cells as ISO 2859-1 / GB/T 2828.1 Table 2-A. Example: H at AQL 0.65 is a
    down arrow to J (n=80, Ac=1, Re=2), and E at AQL 2.5 is a down arrow to F
    (n=20, Ac=1). The last two rows exercise full inspection of small lots.
    """
    result = lookup_aql(lot, aql)
    assert (
        result.code_letter,
        result.effective_code_letter,
        result.sample_size,
        result.acceptance_number,
        result.rejection_number,
    ) == (code, effective, count, acceptance, acceptance + 1)


def test_aql_columns_share_the_published_diagonal_sequence() -> None:
    """Each column's numeric band is a contiguous run of 0, up, down, 1, 2, 3, 5, ..., 21.

    Leading down arrows and trailing up arrows are the open ends of the band; the
    10 column starts at Ac=1 because its Ac=0 plan would lie above code letter A.
    """
    table = load_aql_table()
    sequence = (0, "up", "down", 1, 2, 3, 5, 7, 10, 14, 21)
    assert len(table.columns) == 16
    for column in table.columns.values():
        assert len(column) == len(table.codes)
        start = next(index for index, cell in enumerate(column) if cell != "down")
        end = max(index for index, cell in enumerate(column) if cell != "up") + 1
        band = tuple(column[start:end])
        assert any(sequence[offset : offset + len(band)] == band for offset in range(len(sequence)))


@pytest.mark.parametrize(("lot", "aql"), [(1, 2.5), (0, 2.5), (-1, 2.5), (20, 3.0)])
def test_aql_lookup_outside_declared_scope_rejected(lot: int, aql: float) -> None:
    """Unlisted AQLs never get silently rounded to a more permissive standard column."""
    with pytest.raises(ValidationError, match="supports lots"):
        lookup_aql(lot, aql)


def test_aql_table_documents_historical_source_and_arrow_semantics() -> None:
    """The contract explicitly scopes the public historical standard and numeric unit."""
    table = load_aql_table()
    assert "MIL-STD-105E" in table.standard
    assert "percent defective" in table.scope
    assert "100 percent" in table.arrow_rule
