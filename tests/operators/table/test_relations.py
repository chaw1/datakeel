# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate relationship candidates against independent positive and negative tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.operators.table.models import TableProfile
from datakeel.operators.table.profile import OPERATOR

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.factories import FileFactory


def test_foreign_key_requires_name_and_complete_nonnull_inclusion(
    make_file: FileFactory, output_dir: Path
) -> None:
    """An order's customer key can reference a distinct unique customer identifier."""
    customers = make_file("id,name\nC1,one\nC2,two\n", "customers.csv", "table")
    orders = make_file("id,customer_id\nO1,C1\nO2,C1\nO3,C2\nO4,\n", "orders.csv", "table")
    result = OPERATOR.run([customers, orders], output_dir)
    profile = TableProfile.model_validate(result.files[1].metadata["table_profile"])
    assert len(profile.foreign_keys) == 1
    candidate = profile.foreign_keys[0]
    assert candidate.column == "customer_id"
    assert candidate.referenced_file == "customers.csv"
    assert candidate.referenced_column == "id"
    assert candidate.matched_distinct_values == 2
    assert candidate.coverage == 1


@pytest.mark.parametrize(
    ("reference", "source_name", "source_values"),
    [
        ("id\nC1\nC2\n", "customer_id", ("C1", "unknown")),
        ("id\nC1\nC1\n", "customer_id", ("C1", "C1")),
        ("id\nC1\nC2\n", "color", ("C1", "C2")),
        ("id\nC1\nC2\n", "id", ("C1", "C2")),
        ("id\nC1\nC2\n", "customer_id", ("", "")),
    ],
)
def test_foreign_key_negative_cases_do_not_claim_relationships(
    reference: str,
    source_name: str,
    source_values: tuple[str, str],
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """Overlap without naming, full inclusion or a unique reference is insufficient."""
    customers = make_file(reference, "customers.csv", "table")
    source = source_name + "\n" + "\n".join('"' + value + '"' for value in source_values) + "\n"
    orders = make_file(source, "orders.csv", "table")
    result = OPERATOR.run([customers, orders], output_dir)
    profile = TableProfile.model_validate(result.files[1].metadata["table_profile"])
    assert profile.foreign_keys == ()


def test_matching_explicit_key_names_allow_cross_table_candidates(
    make_file: FileFactory, output_dir: Path
) -> None:
    """A shared explicit entity key is usable even when filenames are unrelated."""
    one = make_file("device_id\nA\nB\n", "inventory.csv", "table")
    two = make_file("device_id\nB\nB\n", "observations.csv", "table")
    result = OPERATOR.run([one, two], output_dir)
    profile = TableProfile.model_validate(result.files[1].metadata["table_profile"])
    assert profile.foreign_keys[0].referenced_column == "device_id"


def test_foreign_key_scan_can_be_disabled(make_file: FileFactory, output_dir: Path) -> None:
    """The scan flag disables cross-file candidate inference entirely."""
    one = make_file("id\nA\nB\n", "devices.csv", "table")
    two = make_file("device_id\nA\nB\n", "readings.csv", "table")
    result = OPERATOR.run([one, two], output_dir, {"detect_foreign_keys": False})
    assert all(not file.metadata["table_profile"]["foreign_keys"] for file in result.files)
