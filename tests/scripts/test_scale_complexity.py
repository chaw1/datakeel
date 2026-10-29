# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The negative control changes complexity while retaining production merge results."""

import pytest

from datakeel.core.models import FileItem
from datakeel.storage import version_diff
from scripts.scale_bench.smoke import Mutation


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ([], []),
        ([], ["a"]),
        (["a"], []),
        (["a", "c"], ["b", "c"]),
        (["a", "a", "c"], ["a", "b", "c", "c"]),
    ],
)
def test_mutation_when_merged_retains_additions_removals_and_duplicate_order(
    before: list[str], after: list[str]
) -> None:
    """A complexity failure cannot be explained by a different functional result."""
    left = [FileItem(id=value, path="", filename=value) for value in before]
    right = [FileItem(id=value, path="", filename=value) for value in after]
    original = version_diff.merge_pairs
    expected = list(original(iter(left), iter(right)))
    with Mutation():
        assert list(version_diff.merge_pairs(iter(left), iter(right))) == expected
    assert version_diff.merge_pairs is original
