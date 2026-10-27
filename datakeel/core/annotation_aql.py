# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read the declared normal single sampling table without approximating acceptance counts."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel

MINIMUM_AQL_LOT_SIZE = 2


class AQLTable(BoundaryModel):
    """Preserve the provenance, supported columns and original arrow cells."""

    standard: str
    source: str
    scope: str
    arrow_rule: str
    lot_upper_bounds: tuple[int | None, ...]
    codes: tuple[str, ...]
    sample_sizes: tuple[int, ...]
    columns: dict[str, tuple[int | Literal["up", "down"], ...]]


class AQLLookup(BoundaryModel):
    """Expose both the initial code and the actual plan selected by a table arrow."""

    code_letter: str
    effective_code_letter: str
    sample_size: int = Field(ge=1)
    acceptance_number: int = Field(ge=0)
    rejection_number: int = Field(ge=1)


def load_aql_table() -> AQLTable:
    """Load the same audited contract in the source tree and installed wheel."""
    packaged = Path(__file__).resolve().parents[1] / "_contracts" / "annotation_qa"
    source = Path(__file__).resolve().parents[2] / "contracts" / "annotation_qa"
    path = (packaged if packaged.is_dir() else source) / "normal-single.json"
    return AQLTable.model_validate_json(path.read_text())


def lookup_aql(lot_size: int, aql: float) -> AQLLookup:
    """Resolve Table I level II and Table II-A, including arrows and full inspection."""
    table = load_aql_table()
    column = table.columns.get(str(float(aql)))
    if lot_size < MINIMUM_AQL_LOT_SIZE or column is None:
        supported = ", ".join(sorted(table.columns, key=float))
        message = f"AQL table supports lots >= 2 and AQL {supported}"
        raise ValidationError(message)
    index = next(
        index
        for index, upper in enumerate(table.lot_upper_bounds)
        if upper is None or lot_size <= upper
    )
    effective = index
    cell = column[effective]
    if isinstance(cell, str):
        step = 1 if cell == "down" else -1
        while isinstance(column[effective], str):
            effective += step
    acceptance = column[effective]
    if not isinstance(acceptance, int):
        message = "Invalid sampling table: arrow has no numeric target"
        raise ValidationError(message)
    return AQLLookup(
        code_letter=table.codes[index],
        effective_code_letter=table.codes[effective],
        sample_size=min(lot_size, table.sample_sizes[effective]),
        acceptance_number=acceptance,
        rejection_number=acceptance + 1,
    )
