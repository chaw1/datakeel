# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise the optional native package's unsigned integer and mode boundaries directly."""

from typing import cast

import datakeel_accel
import pytest

from datakeel.operators.evidence.near_duplicate_hashes import MatchMode, compare_python


@pytest.mark.parametrize("hashes", [[-1], [1 << 64], [1, -1], [1, 1 << 64]])
def test_native_rejects_hashes_outside_u64(hashes: list[int]) -> None:
    """Reject overflow rather than wrapping it into a plausible image hash."""
    with pytest.raises(OverflowError):
        datakeel_accel.compare(hashes)


@pytest.mark.parametrize("hashes", [[1.5], ["1"], [None]])
def test_native_rejects_values_without_integer_conversion(hashes: list[object]) -> None:
    """Floating point and strings cannot silently change the integer-only contract."""
    with pytest.raises(TypeError):
        datakeel_accel.compare(cast("list[int]", hashes))


@pytest.mark.parametrize("threshold", [-1, 65, 1 << 32])
def test_native_rejects_threshold_outside_hash_width(threshold: int) -> None:
    """Enforce the full 0..64 domain before any comparison starts."""
    with pytest.raises((OverflowError, ValueError)):
        datakeel_accel.compare([], threshold=threshold)


@pytest.mark.parametrize("prefix_bits", [-1, 65, 1 << 32])
def test_native_rejects_prefix_outside_hash_width(prefix_bits: int) -> None:
    """A prefix cannot shift past the unsigned hash width."""
    with pytest.raises((OverflowError, ValueError)):
        datakeel_accel.compare([], prefix_bits=prefix_bits)


def test_native_rejects_unknown_mode() -> None:
    """A spelling error must not select either algorithm implicitly."""
    with pytest.raises(ValueError, match="mode"):
        datakeel_accel.compare([], mode=cast("MatchMode", "invalid"))


@pytest.mark.parametrize("prefix_bits", [0, 64])
@pytest.mark.parametrize("mode", ["prefix", "exact"])
def test_native_matches_reference_at_prefix_width_extremes(prefix_bits: int, mode: str) -> None:
    """Keep raw-kernel prefix extremes independent of narrower business contract settings."""
    hashes = [0, 1, (1 << 64) - 1, 1 << 63, 1]
    selected_mode = cast("MatchMode", mode)
    assert datakeel_accel.compare(hashes, 64, prefix_bits, selected_mode) == compare_python(
        hashes, 64, prefix_bits, selected_mode
    )


def test_native_accepts_tuple_input_and_preserves_input_indices() -> None:
    """The public Sequence interface accepts immutable inputs without value-based reordering."""
    assert datakeel_accel.compare((7, 0, 7), threshold=0) == [(0, 2, 0)]
