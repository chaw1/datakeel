# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional extension selection never makes a native package a core dependency."""

from typing import NoReturn, cast

import pytest
from pydantic import ValidationError as PydanticValidationError

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.settings import Settings, get_settings
from datakeel.operators.evidence import near_duplicate_hashes
from datakeel.operators.evidence.near_duplicate_hashes import (
    MatchMode,
    compare_hashes,
    compare_python,
)


def _missing() -> NoReturn:
    raise ModuleNotFoundError(name="datakeel_accel")


def test_auto_when_extension_missing_returns_reference_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh lazy import failure is a supported Python-only installation."""
    monkeypatch.setattr(near_duplicate_hashes, "_load_accel", _missing)
    result = compare_hashes([0, 1], accel="auto")
    assert result.pairs == ((0, 1, 1),)
    assert (result.implementation, result.implementation_version) == ("python", "1.0")


def test_required_when_extension_missing_explains_how_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Required acceleration fails explicitly instead of silently falling back."""
    monkeypatch.setattr(near_duplicate_hashes, "_load_accel", _missing)
    with pytest.raises(ExecutionError, match=r"DATAKEEL_ACCEL=required.*datakeel-accel.*maturin"):
        compare_hashes([], accel="required")


def test_off_does_not_try_to_import_native_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """The disabled path remains independent of native imports and installation state."""

    def unexpected() -> NoReturn:
        pytest.fail("Disabled acceleration attempted an optional import")

    monkeypatch.setattr(near_duplicate_hashes, "_load_accel", unexpected)
    assert compare_hashes([0, 1], accel="off").implementation == "python"


@pytest.mark.parametrize("selection", ["auto", "off", "required"])
def test_acceleration_settings_follow_environment_snapshot(
    monkeypatch: pytest.MonkeyPatch, selection: str
) -> None:
    """Only the prefixed typed setting controls selection, including after environment changes."""
    monkeypatch.setenv("DATAKEEL_ACCEL", selection)
    assert get_settings().accel == selection


def test_acceleration_defaults_auto_and_rejects_unknown_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configuration mistakes are rejected before comparisons start."""
    monkeypatch.delenv("DATAKEEL_ACCEL", raising=False)
    assert Settings().accel == "auto"
    monkeypatch.setenv("DATAKEEL_ACCEL", "sometimes")
    with pytest.raises(PydanticValidationError, match="accel"):
        get_settings()


@pytest.mark.parametrize("hashes", [[-1], [1 << 64]])
def test_reference_rejects_non_u64_hashes(hashes: list[int]) -> None:
    """Python cannot accept integer values that native unsigned arithmetic cannot represent."""
    with pytest.raises(ValidationError, match="unsigned 64-bit"):
        compare_python(hashes)


@pytest.mark.parametrize("threshold", [-1, 65])
def test_reference_rejects_threshold_outside_hash_width(threshold: int) -> None:
    """Reject unsupported Hamming bounds even on empty inputs."""
    with pytest.raises(ValidationError, match="threshold"):
        compare_python([], threshold=threshold)


@pytest.mark.parametrize("prefix_bits", [-1, 65])
def test_reference_rejects_invalid_prefix_width(prefix_bits: int) -> None:
    """Keep prefix memory bounds aligned with the contract and native implementation."""
    with pytest.raises(ValidationError, match="Prefix"):
        compare_python([], prefix_bits=prefix_bits)


def test_reference_rejects_unknown_mode() -> None:
    """Unknown modes cannot quietly select another comparison policy."""
    with pytest.raises(ValidationError, match="mode"):
        compare_python([], mode=cast("MatchMode", "unknown"))


@pytest.mark.parametrize("invalid", [1.5, 8.0, "8", None])
def test_non_integer_inputs_are_rejected_before_backend_selection(invalid: object) -> None:
    """Native and reference dispatch cannot interpret the same float as a different request."""
    value = cast("int", invalid)
    with pytest.raises(ValidationError, match="threshold"):
        compare_python([], threshold=value)
    with pytest.raises(ValidationError, match="Prefix"):
        compare_hashes([], prefix_bits=value, accel="off")
    with pytest.raises(ValidationError, match="unsigned 64-bit"):
        compare_hashes([value], accel="required")


def test_integer_booleans_follow_native_unsigned_integer_semantics() -> None:
    """Python booleans remain accepted as the same integer values understood by PyO3."""
    assert compare_python([False, True], threshold=True, prefix_bits=False) == [(0, 1, 1)]
