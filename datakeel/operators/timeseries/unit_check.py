# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check declared units and ranges without silently converting numeric values."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.table.io import TableData, read_table
from datakeel.operators.timeseries.common import TimePoint, column_index, points, with_summary
from datakeel.operators.timeseries.models import (
    SeriesIssue,
    UnitDeclaration,
    UnitParams,
    UnitSummary,
)
from datakeel.operators.timeseries.parsing import measured_number

UNIT_ALIASES = {"℃": "c", "°c": "c", "celsius": "c", "℉": "f", "°f": "f", "fahrenheit": "f"}


def _canonical(unit: str) -> str:
    compact = unit.strip().casefold().replace(" ", "").replace("³", "3")
    return UNIT_ALIASES.get(compact, compact)


def _problem(
    point: TimePoint, declaration: UnitDeclaration, value: float, unit: str
) -> SeriesIssue | None:
    rule = ""
    threshold = None
    if unit and _canonical(unit) != _canonical(declaration.unit):
        rule = "unit_mismatch"
    elif declaration.minimum is not None and value < declaration.minimum:
        rule, threshold = "unit_range", declaration.minimum
    elif declaration.maximum is not None and value > declaration.maximum:
        rule, threshold = "unit_range", declaration.maximum
    if not rule:
        return None
    detail = (
        f"Explicit unit {unit!r} differs from declared unit {declaration.unit!r}"
        if rule == "unit_mismatch"
        else "Value exceeds the declared unit's inclusive range"
    )
    return SeriesIssue(
        rule=rule,
        column=declaration.column,
        device=point.device,
        rows=(point.row,),
        start_ms=point.milliseconds,
        end_ms=point.milliseconds,
        threshold=threshold,
        observed=value,
        detail=detail,
        recommendation="Verify the source unit and apply an explicit documented conversion",
    )


def _inspect(
    data: TableData, items: list[TimePoint], declarations: list[UnitDeclaration]
) -> tuple[list[SeriesIssue], set[str]]:
    issues: list[SeriesIssue] = []
    units: set[str] = set()
    for declaration in declarations:
        index = column_index(data, declaration.column)
        for point in items:
            parsed = measured_number(data.rows[point.index][index])
            if parsed is None:
                continue
            value, unit = parsed
            if unit:
                units.add(unit)
            issue = _problem(point, declaration, value, unit)
            if issue is not None:
                issues.append(issue)
    return issues, units


def execute(files: list[FileItem], _output_dir: Path, params: UnitParams) -> OperatorResult:
    """Annotate explicit suffix conflicts and physical bounds within device partitions."""
    output: list[FileItem] = []
    issues: list[SeriesIssue] = []
    for file in files:
        data = read_table(file)
        items, invalid = points(data, params)
        detected, units = _inspect(data, items, params.declarations)
        summary = UnitSummary(
            row_count=len(data.rows),
            issues=(*invalid, *detected),
            declarations=tuple(params.declarations),
            observed_units=tuple(sorted(units)),
        )
        output.append(with_summary(file, "unit_check", summary))
        issues.extend(summary.issues)
    return summarize(files, output, [issue.model_dump(mode="json") for issue in issues])


OPERATOR = Operator("timeseries.unit_check", "table", "quality", UnitParams, execute)
