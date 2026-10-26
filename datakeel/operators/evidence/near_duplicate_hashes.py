# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare only 64-bit integers through interchangeable deterministic backends."""

from collections import defaultdict
from collections.abc import Sequence
from importlib import import_module
from itertools import combinations
from typing import Literal, Protocol, cast

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.core.settings import get_settings

MatchMode = Literal["prefix", "exact"]
AccelMode = Literal["auto", "off", "required"]
HashPair = tuple[int, int, int]
PYTHON_VERSION = "1.0"
HASH_BITS = 64
MAX_PREFIX_BITS = HASH_BITS


class HashComparison(BoundaryModel):
    """Bind canonical index pairs to the implementation that measured them."""

    pairs: tuple[HashPair, ...]
    implementation: Literal["python", "rust"]
    implementation_version: str


class _AccelModule(Protocol):
    __version__: str

    def compare(
        self, hashes: Sequence[int], threshold: int, prefix_bits: int, mode: MatchMode
    ) -> list[HashPair]: ...


def _load_accel() -> _AccelModule:
    return cast("_AccelModule", import_module("datakeel_accel"))


def _in_range(value: object, maximum: int) -> bool:
    return isinstance(value, int) and 0 <= value <= maximum


def _validate(hashes: Sequence[int], threshold: int, prefix_bits: int, mode: MatchMode) -> None:
    if not _in_range(threshold, HASH_BITS):
        msg = "Hamming threshold must be an integer between 0 and 64"
        raise ValidationError(msg)
    if not _in_range(prefix_bits, MAX_PREFIX_BITS):
        msg = "Prefix bits must be an integer between 0 and 64"
        raise ValidationError(msg)
    if mode not in {"prefix", "exact"}:
        msg = "Near-duplicate mode must be prefix or exact"
        raise ValidationError(msg)
    if any(not _in_range(value, (1 << HASH_BITS) - 1) for value in hashes):
        msg = "Near-duplicate hashes must be unsigned 64-bit integers"
        raise ValidationError(msg)


def _prefix(hashes: Sequence[int], threshold: int, prefix_bits: int) -> list[HashPair]:
    buckets: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for index, value in enumerate(hashes):
        buckets[value >> (HASH_BITS - prefix_bits)].append((index, value))
    return sorted(
        (left, right, distance)
        for bucket in buckets.values()
        for (left, left_hash), (right, right_hash) in combinations(bucket, 2)
        if (distance := (left_hash ^ right_hash).bit_count()) <= threshold
    )


def _exact(hashes: Sequence[int], threshold: int) -> list[HashPair]:
    if threshold == HASH_BITS:
        return [
            (left, right, (left_hash ^ right_hash).bit_count())
            for (left, left_hash), (right, right_hash) in combinations(enumerate(hashes), 2)
        ]
    width, extra = divmod(HASH_BITS, threshold + 1)
    segments: list[tuple[int, int, dict[int, list[int]]]] = []
    offset = 0
    for segment in range(threshold + 1):
        bits = width + int(segment < extra)
        mask = (1 << bits) - 1
        buckets: dict[int, list[int]] = defaultdict(list)
        for index, value in enumerate(hashes):
            buckets[(value >> offset) & mask].append(index)
        segments.append((offset, mask, buckets))
        offset += bits
    pairs: list[HashPair] = []
    for left, value in enumerate(hashes):
        candidates = {
            right
            for offset, mask, buckets in segments
            for right in buckets[(value >> offset) & mask]
            if right > left
        }
        pairs.extend(
            (left, right, distance)
            for right in sorted(candidates)
            if (distance := (value ^ hashes[right]).bit_count()) <= threshold
        )
    return pairs


def compare_python(
    hashes: Sequence[int], threshold: int = 8, prefix_bits: int = 4, mode: MatchMode = "prefix"
) -> list[HashPair]:
    """Return sorted direct index pairs using prefix blocking or lossless segment indexing."""
    _validate(hashes, threshold, prefix_bits, mode)
    return (
        _prefix(hashes, threshold, prefix_bits) if mode == "prefix" else _exact(hashes, threshold)
    )


def compare_hashes(
    hashes: Sequence[int],
    threshold: int = 8,
    prefix_bits: int = 4,
    mode: MatchMode = "prefix",
    *,
    accel: AccelMode | None = None,
) -> HashComparison:
    """Lazily select the optional extension, making a required installation failure explicit."""
    _validate(hashes, threshold, prefix_bits, mode)
    selection = accel if accel is not None else get_settings().accel
    if selection != "off":
        try:
            extension = _load_accel()
        except (ImportError, OSError) as error:
            if selection == "required":
                msg = (
                    "DATAKEEL_ACCEL=required needs the optional datakeel-accel extension; "
                    "build and install it from accel/ with maturin"
                )
                raise ExecutionError(msg) from error
        else:
            return HashComparison(
                pairs=tuple(extension.compare(hashes, threshold, prefix_bits, mode)),
                implementation="rust",
                implementation_version=extension.__version__,
            )
    return HashComparison(
        pairs=tuple(compare_python(hashes, threshold, prefix_bits, mode)),
        implementation="python",
        implementation_version=PYTHON_VERSION,
    )
