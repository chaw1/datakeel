# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Profile local tables and annotate typed summaries without changing source bytes."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, annotate, summarize
from datakeel.operators.table.inference import infer_type, is_identifier, pii_kinds, value_family
from datakeel.operators.table.io import TableData, read_table
from datakeel.operators.table.models import ColumnProfile, ProfileFinding, TableProfile
from datakeel.operators.table.params import ProfileParams
from datakeel.operators.table.relations import foreign_key_candidates
from datakeel.operators.table.statistics import distribution


def _column_profile(name: str, raw: tuple[str, ...], params: ProfileParams) -> ColumnProfile:
    nulls = {value.strip().casefold() for value in params.null_values}
    values = tuple(value.strip() for value in raw if value.strip().casefold() not in nulls)
    total = len(raw)
    null_count = total - len(values)
    distinct_count = len(set(values))
    inferred_type = infer_type(name, values, params)
    detected_pii = pii_kinds(name, values)
    pii = detected_pii if params.detect_pii else ()
    return ColumnProfile(
        name=name,
        inferred_type=inferred_type,
        null_count=null_count,
        null_rate=null_count / total if total else 0.0,
        distinct_count=distinct_count,
        unique_rate=distinct_count / len(values) if values else 0.0,
        primary_key_candidate=bool(
            values
            and not null_count
            and distinct_count == total
            and is_identifier(name)
            and not detected_pii
        ),
        pii_kinds=pii,
        distribution=distribution(values, inferred_type, detected_pii, params.top_values_limit),
    )


def _column_findings(
    data: TableData, index: int, column: ColumnProfile, params: ProfileParams
) -> tuple[ProfileFinding, ...]:
    findings: list[ProfileFinding] = []
    nulls = {value.strip().casefold() for value in params.null_values}
    rows = tuple(
        (number, row[index].strip())
        for number, row in zip(data.row_numbers, data.rows, strict=True)
    )
    if column.null_count:
        findings.append(
            ProfileFinding(
                code="null_values",
                column=column.name,
                row_numbers=tuple(number for number, value in rows if value.casefold() in nulls),
                count=column.null_count,
                detail=f"{column.null_count} missing values; null rate {column.null_rate:.2%}",
                suggested_action="Review missing values; impute only with a declared policy",
            )
        )
    if column.pii_kinds:
        pii_rows = tuple(number for number, value in rows if pii_kinds(column.name, (value,)))
        findings.append(
            ProfileFinding(
                code="suspected_pii",
                column=column.name,
                row_numbers=pii_rows,
                count=len(pii_rows),
                detail=f"Suspected personal information: {', '.join(column.pii_kinds)}",
                suggested_action="Review access and redact contact values before sharing",
            )
        )
    mixed = _mixed_rows(rows, column, nulls)
    if mixed:
        findings.append(
            ProfileFinding(
                code="mixed_types",
                column=column.name,
                row_numbers=mixed,
                count=len(mixed),
                detail="Values disagree with the majority observed scalar type",
                suggested_action="Declare a column type and repair incompatible values",
            )
        )
    return tuple(findings)


def _mixed_rows(
    rows: tuple[tuple[int, str], ...], column: ColumnProfile, nulls: set[str]
) -> tuple[int, ...]:
    if column.inferred_type != "string" or column.pii_kinds:
        return ()
    nonnull = tuple((number, value) for number, value in rows if value.casefold() not in nulls)
    families = tuple(value_family(value) for _, value in nonnull)
    if not families:
        return ()
    dominant, count = Counter(families).most_common(1)[0]
    if dominant == "string" or count * 2 <= len(nonnull):
        return ()
    return tuple(
        number for (number, _), family in zip(nonnull, families, strict=True) if family != dominant
    )


def profile_data(data: TableData, params: ProfileParams) -> TableProfile:
    """Profile a typed table with source-row findings and no external calls."""
    columns = tuple(
        _column_profile(name, tuple(row[index] for row in data.rows), params)
        for index, name in enumerate(data.columns)
    )
    findings = tuple(
        finding
        for index, column in enumerate(columns)
        for finding in _column_findings(data, index, column, params)
    )
    if not data.rows:
        findings += (
            ProfileFinding(
                code="empty_table",
                severity="error",
                count=0,
                detail="Table contains no data rows",
                suggested_action="Provide a table containing observations",
            ),
        )
    return TableProfile(
        row_count=len(data.rows), column_count=len(columns), columns=columns, findings=findings
    )


def profile_table(path: Path, params: ProfileParams) -> TableProfile:
    """Read and profile one local CSV, TSV or optional Parquet table."""
    file = FileItem(path=str(path), filename=path.name, modality="table")
    return profile_data(read_table(file), params)


def execute(files: list[FileItem], _output_dir: Path, params: ProfileParams) -> OperatorResult:
    """Attach profiles and optional cross-file key candidates to source file metadata."""
    tables = tuple(read_table(file) for file in files)
    profiles = tuple(profile_data(data, params) for data in tables)
    paths = tuple(Path(file.filename) for file in files)
    output: list[FileItem] = []
    final_profiles: list[TableProfile] = []
    for index, (file, base_profile) in enumerate(zip(files, profiles, strict=True)):
        profile = base_profile
        if params.detect_foreign_keys:
            profile = profile.model_copy(
                update={
                    "foreign_keys": foreign_key_candidates(index, paths, tables, profiles, params)
                }
            )
        final_profiles.append(profile)
        output.append(annotate(file, table_profile=profile.model_dump(mode="json")))
    result = summarize(files, output)
    result.quality["issues"] = [
        {"file_id": file.id, **finding.model_dump(mode="json")}
        for file, profile in zip(files, final_profiles, strict=True)
        for finding in profile.findings
    ]
    result.quality["measurements"] = {
        file.id: profile.model_dump(mode="json")
        for file, profile in zip(files, final_profiles, strict=True)
    }
    return result


OPERATOR = Operator("table.profile", "table", "quality", ProfileParams, execute)
