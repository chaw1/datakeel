# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Aggregate confirmed coverage and observed compliance without inferring mappings."""

from collections import defaultdict
from collections.abc import Callable

from datakeel.core.standard_models import (
    ColumnCheck,
    ColumnMapping,
    ColumnProfile,
    CoverageGroup,
    StandardsCoverage,
    ViolationSummary,
)


def _group(
    key: str, profiles: tuple[ColumnProfile, ...], checks: dict[str, ColumnCheck]
) -> CoverageGroup:
    mapped = [profile for profile in profiles if profile.column_id in checks]
    compliant = sum(
        checks[profile.column_id].compliant and checks[profile.column_id].fully_checked
        for profile in mapped
    )
    return CoverageGroup(
        key=key,
        total_columns=len(profiles),
        mapped_columns=len(mapped),
        compliant_columns=compliant,
        coverage=len(mapped) / len(profiles) if profiles else 0,
        compliance=compliant / len(mapped) if mapped else 0,
    )


def _groups(
    profiles: tuple[ColumnProfile, ...],
    checks: dict[str, ColumnCheck],
    key: Callable[[ColumnProfile], str],
) -> tuple[CoverageGroup, ...]:
    groups: dict[str, list[ColumnProfile]] = defaultdict(list)
    for profile in profiles:
        groups[key(profile)].append(profile)
    return tuple(_group(name, tuple(items), checks) for name, items in sorted(groups.items()))


def summarize_coverage(
    profiles: tuple[ColumnProfile, ...],
    mappings: tuple[ColumnMapping, ...],
    checks: tuple[ColumnCheck, ...],
    top_n: int = 10,
) -> StandardsCoverage:
    """Group confirmed mappings; incomplete checks count conservatively as unverified."""
    known = {profile.column_id for profile in profiles}
    confirmed = {item.column_id: item.standard_code for item in mappings if item.column_id in known}
    evaluated = {
        item.column_id: item
        for item in checks
        if confirmed.get(item.column_id) == item.standard_code
    }
    # A confirmed mapping still contributes coverage before a check has been run.
    for column_id, standard_code in confirmed.items():
        if column_id not in evaluated:
            evaluated[column_id] = ColumnCheck(
                column_id=column_id,
                standard_code=standard_code,
                row_count=0,
                skipped_rules=("No check has been run",),
            )
    violations = [
        ViolationSummary(
            column_id=check.column_id,
            standard_code=check.standard_code,
            violation_count=sum(item.count for item in check.violations),
            rules=tuple(item.rule for item in check.violations),
        )
        for check in evaluated.values()
        if check.violations
    ]
    violations.sort(key=lambda item: (-item.violation_count, item.column_id))
    return StandardsCoverage(
        overall=_group("all", profiles, evaluated),
        sources=_groups(profiles, evaluated, lambda item: item.source_id),
        tables=_groups(profiles, evaluated, lambda item: item.table_id),
        owners=_groups(profiles, evaluated, lambda item: item.owner),
        violation_top=tuple(violations[: max(top_n, 0)]),
    )
