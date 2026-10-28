# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise profiling behavior through the actual operator metadata boundary."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.operators.table.io import TableData
from datakeel.operators.table.models import TableProfile
from datakeel.operators.table.params import ProfileParams
from datakeel.operators.table.profile import OPERATOR, execute, profile_data, profile_table

if TYPE_CHECKING:
    from tests.operators.factories import FileFactory


def test_profile_counts_nulls_uniqueness_and_original_evidence_rows() -> None:
    """Null-rate denominators use all rows and unique rates use nonnull values."""
    data = TableData(
        columns=("id", "reading"),
        rows=(("A", "10"), ("B", ""), ("C", "null"), ("D", "10")),
        row_numbers=(12, 15, 19, 22),
    )
    profile = profile_data(data, ProfileParams())
    reading = profile.columns[1]
    assert (profile.row_count, profile.column_count) == (4, 2)
    assert (reading.null_count, reading.null_rate) == (2, 0.5)
    assert (reading.distinct_count, reading.unique_rate) == (1, 0.5)
    assert profile.columns[0].primary_key_candidate
    finding = next(finding for finding in profile.findings if finding.code == "null_values")
    assert finding.column == "reading"
    assert finding.row_numbers == (15, 19)


def test_profile_is_deterministic_and_preserves_source_and_metadata(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Profiling annotates a copy rather than materializing or mutating source data."""
    source = make_file("id,reading\nA,1\nB,2\n", "data.csv", "table")
    source.metadata["origin"] = "generated"
    first = OPERATOR.run([source], output_dir)
    second = OPERATOR.run([source], output_dir)
    assert first == second
    assert first.files[0].path == source.path
    assert first.files[0].metadata["origin"] == "generated"
    assert "table_profile" not in source.metadata
    assert list(output_dir.iterdir()) == []
    assert TableProfile.model_validate(first.files[0].metadata["table_profile"]).row_count == 2


def test_phone_email_findings_never_copy_personal_values_into_profile(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Evidence points to rows while contact values remain in the source only."""
    source = make_file(
        "id,phone,email\nA,13800138000,alice@example.com\nB,13800138001,bob@example.org\n",
        "contacts.csv",
        "table",
    )
    result = OPERATOR.run([source], output_dir)
    profile = TableProfile.model_validate(result.files[0].metadata["table_profile"])
    encoded = profile.model_dump_json()
    assert profile.columns[1].pii_kinds == ("phone",)
    assert profile.columns[2].pii_kinds == ("email",)
    assert "13800138000" not in encoded
    assert "alice@example.com" not in encoded
    assert all(finding.row_numbers == (2, 3) for finding in profile.findings)
    assert {issue["code"] for issue in result.quality["issues"]} == {"suspected_pii"}


def test_mixed_type_finding_identifies_incompatible_rows() -> None:
    """An invalid reading is reported at its original row rather than coerced away."""
    data = TableData(
        columns=("reading",), rows=(("1.2",), ("offline",), ("2.3",)), row_numbers=(8, 11, 15)
    )
    profile = profile_data(data, ProfileParams())
    assert profile.columns[0].inferred_type == "string"
    assert profile.findings[0].code == "mixed_types"
    assert profile.findings[0].row_numbers == (11,)


@pytest.mark.parametrize("content", ["", "id,reading\n"])
def test_empty_tables_report_an_explicit_issue(
    content: str, make_file: FileFactory, output_dir: Path
) -> None:
    """A valid empty input has no fabricated values or inferred primary keys."""
    result = OPERATOR.run([make_file(content, "empty.csv", "table")], output_dir)
    profile = TableProfile.model_validate(result.files[0].metadata["table_profile"])
    assert profile.row_count == 0
    assert profile.findings[0].code == "empty_table"
    assert all(not column.primary_key_candidate for column in profile.columns)


def test_null_markers_are_case_insensitive_and_customizable() -> None:
    """The caller can preserve a business label that resembles a default null marker."""
    data = TableData(
        columns=("value",), rows=((" NONE ",), ("null",), ("",)), row_numbers=(2, 3, 4)
    )
    assert profile_data(data, ProfileParams()).columns[0].null_count == 3
    assert profile_data(data, ProfileParams(null_values=("",))).columns[0].null_count == 1


def test_duplicate_ids_and_missing_ids_are_not_primary_key_candidates() -> None:
    """A key-like name alone cannot establish a plausible primary key."""
    data = TableData(columns=("id",), rows=(("A",), ("A",), ("",)), row_numbers=(2, 3, 4))
    assert not profile_data(data, ProfileParams()).columns[0].primary_key_candidate


def test_profile_table_path_api_matches_operator_metadata(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Catalog import uses the same reader and profile calculation as pipelines."""
    source = make_file("id,reading\nA,1\n", "data.csv", "table")
    expected = profile_table(Path(source.path), ProfileParams())
    result = execute([source], output_dir, ProfileParams())
    assert TableProfile.model_validate(result.files[0].metadata["table_profile"]) == expected


def test_operator_rejects_wrong_modality_and_unknown_params(
    make_file: FileFactory, output_dir: Path
) -> None:
    """The normal operator boundary remains in force for the new implementation."""
    with pytest.raises(ModelValidationError, match="extra_forbidden"):
        OPERATOR.run([], output_dir, {"undeclared": True})
    with pytest.raises(ValueError, match="requires table"):
        OPERATOR.run([make_file("id\n1\n")], output_dir)


def test_disabled_pii_detection_omits_contact_findings() -> None:
    """Disabling contact findings does not opt a summary into copying personal values."""
    data = TableData(columns=("phone",), rows=(("13800138000",),), row_numbers=(2,))
    profile = profile_data(data, ProfileParams(detect_pii=False))
    assert profile.columns[0].pii_kinds == ()
    assert profile.findings == ()
    assert "13800138000" not in profile.model_dump_json()
