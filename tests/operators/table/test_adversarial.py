# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Challenge type and privacy boundaries with conflicting scalar shapes and names."""

import pytest

from datakeel.operators.table.inference import infer_type, pii_kinds
from datakeel.operators.table.io import TableData
from datakeel.operators.table.models import ColumnType
from datakeel.operators.table.params import ProfileParams
from datakeel.operators.table.profile import profile_data


def _profile(name: str, values: tuple[str, ...]) -> str:
    data = TableData(
        columns=(name,),
        rows=tuple((value,) for value in values),
        row_numbers=tuple(range(2, len(values) + 2)),
    )
    return profile_data(data, ProfileParams()).model_dump_json()


@pytest.mark.parametrize("name", ["candidate_phone", "phone_update", "phone_id", "phoneId"])
def test_contact_name_tokens_override_incidental_date_substrings_and_id_hints(name: str) -> None:
    """A contact column must remain protected when another token resembles a date or ID."""
    values = ("+1 (415) 555-0132", "13800138000")
    assert pii_kinds(name, values) == ("phone",)
    encoded = _profile(name, values)
    assert "13800138000" not in encoded
    assert "415" not in encoded


@pytest.mark.parametrize("name", ["record_id", "recordId", "timestamp"])
def test_formatted_contacts_cannot_bypass_privacy_using_a_misleading_column_name(name: str) -> None:
    """Scalar-name hints disambiguate plain numbers without exempting obvious contacts."""
    value = "+1 (415) 555-0132"
    assert pii_kinds(name, (value,)) == ("phone",)
    assert value not in _profile(name, (value,))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("event_at", "1700000000"),
        ("eventAt", "1700000000"),
        ("ts", "1700000000"),
        ("reading", "1700000000"),
        ("serial_number", "12345678901"),
        ("recordId", "13800138000"),
        ("amount", "13800138000"),
        ("price", "13800138000.25"),
        ("reading", "13800138000.25"),
        ("reading", "13800138000e-1"),
        ("reading", "$13,800,138,000.25"),
        ("phone", "12345678901234567890123"),
        ("phone", "2026-10-27"),
    ],
)
def test_numeric_epochs_ids_amounts_and_dates_are_not_phone_evidence(name: str, value: str) -> None:
    """A numeric prefix inside another scalar shape does not establish a phone value."""
    assert pii_kinds(name, (value,)) == ()


def test_phone_pattern_scan_does_not_stop_at_an_unrelated_short_number() -> None:
    """An earlier ambiguous numeric span cannot conceal a later obvious contact."""
    text = "code 123456789; call +1 (415) 555-0132"
    assert pii_kinds("notes", (text,)) == ("phone",)


@pytest.mark.parametrize(
    ("name", "values", "expected"),
    [
        ("recordId", ("000001", "000002"), "identifier"),
        ("sku", ("000001", "000002"), "identifier"),
        ("serial_number", ("12345678901", "12345678902"), "identifier"),
        ("price", ("-$1,200.20", "+$50.25"), "amount"),
        ("observed_on", ("2026-10-27", "2026-10-28T00:00:00Z"), "datetime"),
    ],
)
def test_semantic_name_and_value_conflicts_remain_conservative(
    name: str, values: tuple[str, ...], expected: ColumnType
) -> None:
    """IDs retain leading zeroes, valid money retains numeric semantics and dates agree."""
    assert infer_type(name, values, ProfileParams()) == expected


def test_mixed_category_values_do_not_accuse_valid_text_labels() -> None:
    """An enum may intentionally combine numeric codes and textual states."""
    values = ("0",) * 10 + ("off",) * 10
    data = TableData(
        columns=("state",),
        rows=tuple((value,) for value in values),
        row_numbers=tuple(range(2, 22)),
    )
    profile = profile_data(data, ProfileParams())
    assert profile.columns[0].inferred_type == "enum"
    assert not profile.findings


def test_one_numeric_category_does_not_make_all_text_rows_invalid() -> None:
    """A lone number cannot define the intended type of a mostly textual column."""
    values = ("1", "normal", "warm", "off", "waiting")
    data = TableData(
        columns=("state",), rows=tuple((value,) for value in values), row_numbers=(2, 3, 4, 5, 6)
    )
    assert not profile_data(data, ProfileParams()).findings


@pytest.mark.parametrize(
    "values",
    [
        ("2026-10-01", "invalid", "2026-10-02T00:00:00Z"),
        ("true", "invalid", "false"),
        ("$1,200.00", "invalid", "1200"),
        ("1", "inf", "2"),
        ("1", "NaN", "2"),
    ],
)
def test_majority_scalar_type_anchors_incompatible_rows_without_coercion(
    values: tuple[str, ...],
) -> None:
    """Dates, booleans and numeric/amount values share the same majority-only rule."""
    data = TableData(
        columns=("reading",), rows=tuple((value,) for value in values), row_numbers=(20, 30, 40)
    )
    profile = profile_data(data, ProfileParams(null_values=("",)))
    assert profile.columns[0].distribution.numeric is None
    assert profile.findings[0].code == "mixed_types"
    assert profile.findings[0].row_numbers == (30,)


def test_nan_default_is_missing_and_infinite_tokens_never_become_finite_statistics() -> None:
    """Default NaN handling is explicit null evidence; infinities remain untyped text."""
    data = TableData(
        columns=("reading",), rows=(("NaN",), ("inf",), ("-inf",)), row_numbers=(2, 3, 4)
    )
    profile = profile_data(data, ProfileParams())
    assert profile.columns[0].null_count == 1
    assert profile.columns[0].distribution.numeric is None
    assert profile.findings[0].code == "null_values"
    assert profile.findings[0].row_numbers == (2,)
