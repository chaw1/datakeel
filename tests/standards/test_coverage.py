# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Coverage denominators retain unconfirmed and unverified columns correctly."""

from datakeel.core.standard_models import (
    ColumnCheck,
    ColumnMapping,
    ColumnProfile,
    StandardViolation,
)
from datakeel.standards.coverage import summarize_coverage


def _profile(column_id: str, source: str, table: str, owner: str) -> ColumnProfile:
    return ColumnProfile(
        column_id=column_id,
        name=column_id,
        data_type="TEXT",
        source_id=source,
        table_id=table,
        owner=owner,
    )


def test_coverage_counts_confirmed_mappings_and_observed_compliance() -> None:
    """Ratios use the full inventory and retain source, table and owner grouping."""
    profiles = (
        _profile("a", "crm", "crm.customers", "steward"),
        _profile("b", "crm", "crm.customers", "steward"),
        _profile("c", "erp", "erp.products", "owner"),
    )
    mappings = (
        ColumnMapping(column_id="a", standard_code="x"),
        ColumnMapping(column_id="b", standard_code="x"),
    )
    checks = (
        ColumnCheck(column_id="a", standard_code="x", row_count=1, checked_rules=("type",)),
        ColumnCheck(
            column_id="b",
            standard_code="x",
            row_count=1,
            checked_rules=("type",),
            violations=(StandardViolation(rule="type", count=1, message="Mismatch"),),
        ),
    )
    result = summarize_coverage(profiles, mappings, checks)
    assert result.overall.total_columns == 3
    assert result.overall.coverage == 2 / 3
    assert result.overall.compliance == 0.5
    assert result.sources[0].key == "crm"
    assert result.tables[0].mapped_columns == 2
    assert result.owners[1].coverage == 1
    assert result.violation_top[0].column_id == "b"


def test_mapping_without_completed_check_counts_coverage_only() -> None:
    """Confirming a mapping never manufactures successful data checks."""
    result = summarize_coverage(
        (_profile("a", "s", "t", "o"),), (ColumnMapping(column_id="a", standard_code="x"),), ()
    )
    assert result.overall.coverage == 1
    assert result.overall.compliance == 0


def test_partial_checks_cannot_claim_full_compliance() -> None:
    """Missing source data remains unverified even when metadata constraints pass."""
    result = summarize_coverage(
        (_profile("a", "s", "t", "o"),),
        (ColumnMapping(column_id="a", standard_code="x"),),
        (
            ColumnCheck(
                column_id="a",
                standard_code="x",
                row_count=0,
                checked_rules=("type",),
                skipped_rules=("range: no observed evidence",),
            ),
        ),
    )
    assert result.overall.compliant_columns == 0


def test_stale_checks_and_unknown_columns_are_not_counted() -> None:
    """A check against an old standard cannot satisfy a replacement confirmed mapping."""
    result = summarize_coverage(
        (_profile("a", "s", "t", "o"),),
        (
            ColumnMapping(column_id="a", standard_code="new"),
            ColumnMapping(column_id="missing", standard_code="x"),
        ),
        (ColumnCheck(column_id="a", standard_code="old", row_count=1),),
    )
    assert result.overall.mapped_columns == 1
    assert result.overall.compliant_columns == 0


def test_empty_coverage_has_zero_denominators_and_no_groups() -> None:
    """An empty inventory stays explicit instead of reporting artificial success."""
    result = summarize_coverage((), (), ())
    assert result.overall.coverage == result.overall.compliance == 0
    assert not result.sources


def test_violation_top_is_stable_bounded_and_sorted() -> None:
    """Descending violation counts use column identity as a deterministic tie break."""
    profiles = tuple(_profile(name, "s", "t", "o") for name in ("b", "a", "c"))
    mappings = tuple(
        ColumnMapping(column_id=item.column_id, standard_code="x") for item in profiles
    )
    checks = tuple(
        ColumnCheck(
            column_id=item.column_id,
            standard_code="x",
            row_count=10,
            violations=(
                StandardViolation(
                    rule="range", count=5 if item.column_id != "c" else 10, message="Outside"
                ),
            ),
        )
        for item in profiles
    )
    assert [
        item.column_id
        for item in summarize_coverage(profiles, mappings, checks, top_n=2).violation_top
    ] == ["c", "a"]
    assert not summarize_coverage(profiles, mappings, checks, top_n=-1).violation_top
