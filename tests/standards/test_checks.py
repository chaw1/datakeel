# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise every declared violation independently and prevent sample disclosure."""

from decimal import Decimal

import pytest

from datakeel.core.standard_models import (
    CodeEntry,
    CodeList,
    ColumnProfile,
    FieldStandard,
    StandardsContract,
    ViolationRule,
)
from datakeel.standards.checks import check_column


def _standard(**changes: object) -> FieldStandard:
    return FieldStandard.model_validate(
        {
            "code": "sample",
            "name_zh": "测试字段",
            "name_en": "sample",
            "description": "Generated fixture",
            "data_type": "string",
            "status": "active",
            **changes,
        }
    )


@pytest.mark.parametrize(
    ("changes", "profile", "rule", "count"),
    [
        (
            {"data_type": "integer"},
            ColumnProfile(column_id="x", name="x", data_type="TEXT", values=("bad",)),
            "type",
            1,
        ),
        (
            {"length": 3},
            ColumnProfile(column_id="x", name="x", data_type="TEXT", values=("ok", "longer")),
            "length",
            1,
        ),
        (
            {"data_type": "number", "precision": 4, "scale": 2},
            ColumnProfile(
                column_id="x", name="x", data_type="NUMERIC", values=(12.34, 123.45, 1.234)
            ),
            "precision",
            2,
        ),
        (
            {"code_list": "status"},
            ColumnProfile(column_id="x", name="x", data_type="TEXT", values=("ok", "no")),
            "code_list",
            1,
        ),
        (
            {"data_type": "integer", "minimum": 0, "maximum": 100},
            ColumnProfile(column_id="x", name="x", data_type="INT", values=(-1, 0, 100, 101)),
            "range",
            2,
        ),
        (
            {"pattern": r"P\d{3}"},
            ColumnProfile(
                column_id="x", name="x", data_type="TEXT", values=("P001", "X001", "P001x")
            ),
            "pattern",
            2,
        ),
        (
            {"required": True},
            ColumnProfile(column_id="x", name="x", data_type="TEXT", values=("ok", None, "")),
            "required",
            2,
        ),
        (
            {"unit": "CNY"},
            ColumnProfile(column_id="x", name="x", data_type="TEXT", unit="USD", values=("12",)),
            "unit",
            1,
        ),
        (
            {"sensitivity": "internal"},
            ColumnProfile(
                column_id="x", name="x", data_type="TEXT", values=("person@example.com",)
            ),
            "sensitivity",
            1,
        ),
    ],
)
def test_each_constraint_detects_exact_bad_values(
    changes: dict[str, object],
    profile: ColumnProfile,
    rule: ViolationRule,
    count: int,
) -> None:
    """Each isolated seeded error produces precisely the intended rule and count."""
    codes = (
        CodeList(code="status", name="Status", entries=(CodeEntry(value="ok", label_zh="有效"),)),
    )
    result = check_column(profile, _standard(**changes), codes)
    assert [(item.rule, item.count) for item in result.violations] == [(rule, count)]
    assert not result.compliant
    assert result.fully_checked


@pytest.mark.parametrize(
    ("definition", "profile"),
    [
        (
            {"length": 5, "required": True, "pattern": "[a-z]+"},
            ColumnProfile(column_id="x", name="x", data_type="VARCHAR(5)", values=("alice", "bob")),
        ),
        (
            {"data_type": "number", "precision": 6, "scale": 2, "minimum": 0, "maximum": 100},
            ColumnProfile(column_id="x", name="x", data_type="INTEGER", values=(1, 20, 100)),
        ),
        (
            {"unit": "CNY", "sensitivity": "confidential"},
            ColumnProfile(
                column_id="x",
                name="x",
                data_type="TEXT",
                unit="CNY",
                values=("person@example.com",),
            ),
        ),
        (
            {"code_list": "status"},
            ColumnProfile(column_id="x", name="x", data_type="TEXT", values=("ok", None)),
        ),
    ],
)
def test_valid_values_have_no_false_violations(
    definition: dict[str, object],
    profile: ColumnProfile,
) -> None:
    """Valid boundary values and optional nulls pass without false positives."""
    codes = (
        CodeList(code="status", name="Status", entries=(CodeEntry(value="ok", label_zh="有效"),)),
    )
    assert check_column(profile, _standard(**definition), codes).compliant


def test_violation_samples_use_shared_pii_redaction() -> None:
    """Even a public standard cannot expose email or phone samples in reports."""
    profile = ColumnProfile(
        column_id="x",
        name="x",
        data_type="TEXT",
        values=(
            "person@example.com",
            "+1 202 555 0108",
        ),
    )
    result = check_column(profile, _standard(length=1, sensitivity="public"))
    samples = [sample for item in result.violations for sample in item.samples]
    assert samples
    assert all("person" not in sample and "202" not in sample for sample in samples)


def test_confidential_samples_are_fully_masked() -> None:
    """Sensitive personal names are masked even when no PII regex recognizes them."""
    result = check_column(
        ColumnProfile(
            column_id="x", name="name", data_type="TEXT", values=("Generated Sample Person",)
        ),
        _standard(length=3, sensitivity="confidential"),
    )
    assert result.violations[0].samples == ("[REDACTED]",)


def test_sensitivity_declared_conflict_without_values_is_detected() -> None:
    """Known classification metadata can establish a conflict without reading values."""
    result = check_column(
        ColumnProfile(
            column_id="x",
            name="x",
            data_type="TEXT",
            sensitivity="restricted",
        ),
        _standard(sensitivity="public"),
    )
    assert result.violations[0].rule == "sensitivity"


def test_missing_observations_preserve_unknown_rules() -> None:
    """Unavailable value or unit evidence never becomes a claimed successful check."""
    result = check_column(
        ColumnProfile(column_id="x", name="x", data_type="TEXT"),
        _standard(
            required=True,
            length=10,
            precision=3,
            scale=1,
            minimum=0,
            pattern=".*",
            unit="CNY",
            code_list="unknown",
        ),
    )
    assert result.checked_rules == ("type",)
    assert len(result.skipped_rules) == 8
    assert not result.fully_checked
    assert result.compliant


def test_missing_unit_with_observed_values_is_unknown() -> None:
    """Observed data cannot supply missing measurement-unit metadata."""
    result = check_column(
        ColumnProfile(
            column_id="x",
            name="x",
            data_type="TEXT",
            values=("25",),
        ),
        _standard(unit="CNY"),
    )
    assert result.skipped_rules == ("unit: no observed evidence",)
    assert not result.violations


def test_declared_length_and_precision_limits_are_checked() -> None:
    """Oversized SQL column declarations fail even if current values fit."""
    profile = ColumnProfile(
        column_id="x", name="x", data_type="NUMERIC", length=40, precision=8, scale=4
    )
    result = check_column(profile, _standard(data_type="number", length=20, precision=6, scale=2))
    assert {item.rule for item in result.violations} == {"length", "precision"}


def test_required_uses_observed_null_count_without_raw_samples() -> None:
    """An exact aggregate null count can establish completeness failure independently."""
    result = check_column(
        ColumnProfile(
            column_id="x",
            name="x",
            data_type="TEXT",
            row_count=10,
            null_count=4,
        ),
        _standard(required=True),
    )
    assert result.violations[0].count == 4
    assert result.violations[0].samples == ()


def test_numeric_code_identity_does_not_coerce_strings_or_booleans() -> None:
    """Reference values preserve scalar types instead of accepting ambiguous coercions."""
    codes = (CodeList(code="bits", name="Bits", entries=(CodeEntry(value=1, label_zh="是"),)),)
    result = check_column(
        ColumnProfile(
            column_id="x",
            name="x",
            data_type="TEXT",
            values=("1",),
        ),
        _standard(code_list="bits"),
        codes,
    )
    assert result.violations[0].rule == "code_list"


def test_integer_and_boolean_value_types_remain_distinct() -> None:
    """A boolean value does not satisfy an integer field despite Python subclassing."""
    result = check_column(
        ColumnProfile(
            column_id="x",
            name="x",
            data_type="INTEGER",
            values=(True,),
        ),
        _standard(data_type="integer"),
    )
    assert result.violations[0].rule == "type"


def test_enterprise_standards_validate_generated_examples(contract: StandardsContract) -> None:
    """The public contract's clean business examples introduce no false positives."""
    samples = {
        "customer_id": (1, 2),
        "customer_name": ("样例客户一", "样例客户二"),
        "customer_email": ("first@example.com",),
        "customer_status": ("active", "inactive"),
        "customer_age": (0, 150),
        "revenue": (0.0, 999.99),
        "order_date": ("2026-10-27",),
    }
    for standard in contract.standards:
        if standard.code in samples:
            result = check_column(
                ColumnProfile(
                    column_id=standard.code,
                    name=standard.name_en,
                    data_type=standard.data_type,
                    values=samples[standard.code],
                    unit=standard.unit,
                ),
                standard,
                contract.code_lists,
            )
            assert result.compliant, result


def test_unknown_declared_type_is_skipped_even_when_values_exist() -> None:
    """A missing reflected physical type cannot become a successful type check."""
    result = check_column(
        ColumnProfile(column_id="x", name="x", data_type="unknown", values=(1,)),
        _standard(data_type="integer"),
    )
    assert "type" not in result.checked_rules
    assert "type: no observed evidence" in result.skipped_rules
    assert all(item.rule != "type" for item in result.violations)


def test_integral_numeric_value_does_not_fail_zero_scale() -> None:
    """Insignificant decimal zeroes do not count as fractional precision."""
    assert check_column(
        ColumnProfile(column_id="x", name="x", data_type="NUMERIC", values=(1.0, 0.0)),
        _standard(data_type="number", precision=4, scale=0),
    ).compliant


def test_boolean_and_unknown_value_type_paths_are_explicit() -> None:
    """Boolean fields reject integer values while user-defined types use metadata."""
    boolean = check_column(
        ColumnProfile(column_id="x", name="x", data_type="BOOLEAN", values=(1,)),
        _standard(data_type="boolean"),
    )
    custom = check_column(
        ColumnProfile(column_id="x", name="x", data_type="CUSTOM", values=("ok",)),
        _standard(data_type="custom"),
    )
    assert boolean.violations[0].rule == "type"
    assert custom.compliant


def test_non_numeric_range_values_are_violations() -> None:
    """Invalid numeric representations cannot silently satisfy numeric range bounds."""
    result = check_column(
        ColumnProfile(column_id="x", name="x", data_type="INTEGER", values=("bad",)),
        _standard(data_type="integer", minimum=0),
    )
    assert {item.rule for item in result.violations} == {"type", "range"}


def test_truncated_population_retains_observed_results_but_cannot_claim_full_compliance() -> None:
    """A clean bounded sample cannot stand in for the unobserved source population."""
    result = check_column(
        ColumnProfile(
            column_id="x",
            name="x",
            data_type="TEXT",
            values=("clean",),
            row_count=1,
            truncated=True,
        ),
        _standard(),
    )
    assert result.compliant
    assert not result.fully_checked
    assert result.row_count == 1
    assert result.skipped_rules == ("source_population: truncated after 1 observed rows",)


@pytest.mark.parametrize("status", ["draft", "deprecated"])
def test_ineffective_standard_cannot_claim_current_conformance(status: str) -> None:
    """Historical mappings retain identity while ineffective definitions remain unverified."""
    definition = FieldStandard.model_validate({**_standard().model_dump(), "status": status})
    result = check_column(
        ColumnProfile(column_id="x", name="x", data_type="TEXT", values=("clean",)), definition
    )
    assert not result.checked_rules
    assert not result.fully_checked
    assert result.skipped_rules == (f"standard_status: {status} is ineffective",)


def test_profile_classification_overrides_lower_standard_for_all_samples() -> None:
    """A sensitivity conflict cannot reveal names through another constraint's samples."""
    result = check_column(
        ColumnProfile(
            column_id="x",
            name="x",
            data_type="TEXT",
            sensitivity="restricted",
            values=("Generated Person One", "Generated Person Two"),
        ),
        _standard(length=1, sensitivity="public"),
    )
    assert {item.rule for item in result.violations} == {"length", "sensitivity"}
    assert result.violations[0].samples == ("[REDACTED]",)
    assert "Generated Person" not in result.model_dump_json()


def test_decimal_precision_preserves_all_significant_digits() -> None:
    """Exact numeric observations beyond binary-float precision still trigger scale limits."""
    profile = ColumnProfile(
        column_id="x",
        name="x",
        data_type="NUMERIC",
        values=(Decimal("12345678901234567890.123456789012345678"),),
    )
    assert isinstance(profile.values[0], Decimal)
    result = check_column(
        profile, _standard(data_type="number", precision=40, scale=17, sensitivity="confidential")
    )
    assert [(item.rule, item.count) for item in result.violations] == [("precision", 1)]


def test_decimal_bounds_compare_exact_decimal_business_values() -> None:
    """A decimal boundary equal to 0.1 is not compared against a binary approximation."""
    result = check_column(
        ColumnProfile(column_id="x", name="x", data_type="NUMERIC", values=(Decimal("0.1"),)),
        _standard(data_type="number", minimum=0.1, maximum=0.1),
    )
    assert result.compliant


def test_numeric_reference_codes_match_exact_decimals_without_text_coercion() -> None:
    """SQL NUMERIC representations can match integer codes without accepting text codes."""
    codes = (CodeList(code="bits", name="Bits", entries=(CodeEntry(value=1, label_zh="是"),)),)
    result = check_column(
        ColumnProfile(column_id="x", name="x", data_type="NUMERIC", values=(Decimal("1.000"),)),
        _standard(data_type="number", code_list="bits"),
        codes,
    )
    assert result.compliant


@pytest.mark.parametrize("value", [1234567890123, Decimal("123456789.12")])
def test_numeric_amounts_and_long_keys_do_not_infer_personal_information(
    value: int | Decimal,
) -> None:
    """Numeric magnitude alone is not evidence that a column contains phone numbers."""
    result = check_column(
        ColumnProfile(column_id="x", name="x", data_type="NUMERIC", values=(value,)),
        _standard(data_type="number", sensitivity="public"),
    )
    assert result.compliant
