# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Select one optional training fingerprint kernel without changing its byte contract."""

from collections.abc import Callable
from functools import lru_cache
from importlib import import_module
from typing import Literal, Protocol, cast

from datakeel.core.errors import ExecutionError
from datakeel.core.settings import get_settings
from datakeel.llm_data.similarity import (
    MIN_LENGTH_RATIO,
    SHORT_TEXT_LENGTH,
    fingerprint,
    similarity,
)

type Fingerprint = Callable[[str], tuple[int, tuple[bytes, ...]]]
type Similarity = Callable[[str, str], float]
_BAND_BYTES = 17
_BAND_COUNT = 8
_MAX_CACHED_TEXT = 4096
_CACHED_SHINGLES = 4096


class _Kernel(Protocol):
    def __call__(self, text: str) -> tuple[int, bytes]: ...


class _Shingles(Protocol):
    def __call__(self, text: str) -> bytes: ...


class _Dice(Protocol):
    def __call__(self, left: bytes, right: bytes) -> float: ...


def _load_kernel() -> _Kernel:
    extension = import_module("datakeel_accel")
    candidate: object = getattr(extension, "training_fingerprint", None)
    if not callable(candidate):
        message = "The optional extension has no training fingerprint kernel"
        raise TypeError(message)
    return cast("_Kernel", candidate)


def resolve_fingerprint(*, accel: Literal["auto", "off", "required"] | None = None) -> Fingerprint:
    """Resolve once per index; old or absent auto extensions retain the Python fallback."""
    selection = get_settings().accel if accel is None else accel
    if selection == "off":
        return fingerprint
    try:
        kernel = _load_kernel()
    except (ImportError, OSError, TypeError) as error:
        if selection == "required":
            message = (
                "DATAKEEL_ACCEL=required needs the optional datakeel-accel training "
                "fingerprint kernel; rebuild and install it from accel/ with maturin"
            )
            raise ExecutionError(message) from error
        return fingerprint

    def accelerated(text: str) -> tuple[int, tuple[bytes, ...]]:
        hashed, packed = kernel(text)
        if len(packed) != _BAND_COUNT * _BAND_BYTES:
            message = "Optional training fingerprint returned an invalid band width"
            raise ExecutionError(message)
        return hashed, tuple(
            packed[offset : offset + _BAND_BYTES] for offset in range(0, len(packed), _BAND_BYTES)
        )

    return accelerated


def _load_similarity() -> tuple[_Shingles, _Dice]:
    extension = import_module("datakeel_accel")
    shingles: object = getattr(extension, "training_shingles", None)
    dice: object = getattr(extension, "training_dice", None)
    if not callable(shingles) or not callable(dice):
        message = "The optional extension has no training similarity kernels"
        raise TypeError(message)
    return cast("_Shingles", shingles), cast("_Dice", dice)


def resolve_similarity(*, accel: Literal["auto", "off", "required"] | None = None) -> Similarity:
    """Cache bounded exact packed shingles while preserving short-text edit confirmation."""
    selection = get_settings().accel if accel is None else accel
    if selection == "off":
        return similarity
    try:
        shingles, dice = _load_similarity()
    except (ImportError, OSError, TypeError) as error:
        if selection == "required":
            message = (
                "DATAKEEL_ACCEL=required needs the optional datakeel-accel training "
                "similarity kernels; rebuild and install it from accel/ with maturin"
            )
            raise ExecutionError(message) from error
        return similarity

    cached = lru_cache(maxsize=_CACHED_SHINGLES)(shingles)

    def blobs(text: str) -> bytes:
        return cached(text) if len(text) <= _MAX_CACHED_TEXT else shingles(text)

    def accelerated(left: str, right: str) -> float:
        if max(len(left), len(right)) <= SHORT_TEXT_LENGTH:
            return similarity(left, right)
        if left == right:
            return 1
        if min(len(left), len(right)) / max(1, len(left), len(right)) < MIN_LENGTH_RATIO:
            return 0
        return dice(blobs(left), blobs(right))

    return accelerated
