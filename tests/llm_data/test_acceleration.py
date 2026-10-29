# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check optional-kernel selection and exact training fingerprint interoperability."""

import random
import struct
from collections import Counter
from collections.abc import Callable
from types import SimpleNamespace
from typing import Never

import pytest

from datakeel.core.errors import ExecutionError
from datakeel.llm_data import acceleration
from datakeel.llm_data.acceleration import resolve_fingerprint, resolve_similarity
from datakeel.llm_data.similarity import fingerprint, normalize, similarity


def test_off_when_extension_loading_would_fail_preserves_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit off never imports the optional extension."""

    def unavailable() -> Never:
        message = "This loader must not be called"
        raise AssertionError(message)

    monkeypatch.setattr(acceleration, "_load_kernel", unavailable)
    monkeypatch.setattr(acceleration, "_load_similarity", unavailable)
    assert resolve_fingerprint(accel="off") is fingerprint
    assert resolve_similarity(accel="off") is similarity


@pytest.mark.parametrize("failure", [ImportError("Absent"), OSError("Unavailable")])
def test_auto_when_optional_kernel_is_unavailable_retains_python(
    failure: ImportError | OSError, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing packages and unloadable native libraries keep the existing byte contract."""

    def unavailable() -> Never:
        raise failure

    monkeypatch.setattr(acceleration, "_load_kernel", unavailable)
    monkeypatch.setattr(acceleration, "_load_similarity", unavailable)
    assert resolve_fingerprint(accel="auto") is fingerprint
    assert resolve_similarity(accel="auto") is similarity


def test_old_extension_when_training_function_is_missing_has_explicit_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older comparison-only wheels fall back automatically and fail clearly if required."""

    def old_extension(_name: str) -> SimpleNamespace:
        return SimpleNamespace(__version__="0.1.0", compare=None)

    monkeypatch.setattr(acceleration, "import_module", old_extension)
    assert resolve_fingerprint(accel="auto") is fingerprint
    assert resolve_similarity(accel="auto") is similarity
    message = ""
    try:
        resolve_fingerprint(accel="required")
    except ExecutionError as error:
        message = str(error)
    assert "training fingerprint kernel" in message
    message = ""
    try:
        resolve_similarity(accel="required")
    except ExecutionError as error:
        message = str(error)
    assert "training similarity kernels" in message


def test_native_fingerprint_when_unicode_and_feature_sampling_vary_matches_every_byte() -> None:
    """Real native results equal the independent unchanged Python implementation."""
    native = resolve_fingerprint(accel="required")
    rng = random.Random(2026102903)  # noqa: S311  # Reproducible generated differential cases.
    alphabet = "abcdefxyz0123456789中文河流观察模型比较\u0301\U00020000\U00020001\U0001f603"
    texts = [
        "",
        "a",
        "ab",
        "abc",
        "aaa",
        "a" * 2000,
        "中文",
        "你好\uff0c世界\uff01",
        "\uff28\uff45\uff4c\uff4c\uff4f WORLD!",
        "Straße STRASSE",
        "é e\u0301",
        "a\x00b\nc\td",
    ]
    for size in (1, 2, 3, 10, 255, 256, 257, 511, 512, 513, 1000, 3000):
        texts.extend("".join(rng.choices(alphabet, k=size)) for _ in range(12))
    for text in texts:
        normalized = normalize(text)
        assert native(normalized) == fingerprint(normalized)
        assert native(text) == fingerprint(text)


def test_native_band_width_when_invalid_is_rejected_with_a_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed but malformed native result cannot become a different index layout."""

    def malformed(_text: str) -> tuple[int, bytes]:
        return 1, b"invalid"

    def extension(_name: str) -> SimpleNamespace:
        return SimpleNamespace(training_fingerprint=malformed)

    monkeypatch.setattr(acceleration, "import_module", extension)
    selected = resolve_fingerprint(accel="required")
    message = ""
    try:
        selected("generated text")
    except ExecutionError as error:
        message = str(error)
    assert "invalid band width" in message


def test_native_similarity_when_lengths_and_scripts_vary_matches_python_float_bits() -> None:
    """Exact packed Dice preserves decisions, float bits and short-text edit matching."""
    selected = resolve_similarity(accel="required")
    rng = random.Random(2026102904)  # noqa: S311  # Reproducible generated differential cases.
    alphabet = "abcdefghijklmnopqrstuvwxyz中文河流观察\u0301\U00020000\U0001f603\x00"
    cases = [("", ""), ("a", "b"), ("abcdef", "abcdxf")]
    for size in (255, 256, 257, 500, 4096, 4097, 6000):
        left = "".join(rng.choices(alphabet, k=size))
        changed = left[: size // 2] + "字" + left[size // 2 + 1 :]
        cases.extend(
            [
                (left, left),
                (left, changed),
                (left, left[: size * 3 // 4]),
                (left, left[: size * 3 // 4 - 1]),
                (left, "".join(rng.choices(alphabet, k=size))),
            ]
        )
    cases.extend(
        [
            ("abcdefgh" * 60, "abcdxfgh" * 60),
            ("中文河流观察" * 60, "中文河流模型" * 60),
            ("abcd" * 64, "abce" * 64),
            ("abcd" * 64 + "e", "abce" * 64 + "f"),
        ]
    )
    for left, right in cases:
        assert struct.pack("!d", selected(left, right)) == struct.pack(
            "!d", similarity(left, right)
        )


def test_native_similarity_when_text_is_short_uses_original_edit_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Short SequenceMatcher cases never enter the long-text Dice kernel."""

    def forbidden(_text: str) -> bytes:
        message = "Short text must use the original similarity function"
        raise AssertionError(message)

    def dice(_left: bytes, _right: bytes) -> float:
        return 0

    def kernels() -> tuple[Callable[[str], bytes], Callable[[bytes, bytes], float]]:
        return forbidden, dice

    monkeypatch.setattr(acceleration, "_load_similarity", kernels)
    selected = resolve_similarity(accel="required")
    left, right = "abcdefgh" * 20, "abcdxfgh" * 20
    assert selected(left, right) == similarity(left, right)


def test_native_similarity_cache_when_entries_or_text_grow_stays_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configured entry limit evicts old sets; larger texts bypass memoization."""
    calls: Counter[str] = Counter()

    def shingles(text: str) -> bytes:
        calls[text] += 1
        return b"\0" * 8

    def dice(_left: bytes, _right: bytes) -> float:
        return 0.5

    def kernels() -> tuple[Callable[[str], bytes], Callable[[bytes, bytes], float]]:
        return shingles, dice

    monkeypatch.setattr(acceleration, "_load_similarity", kernels)
    monkeypatch.setattr(acceleration, "_CACHED_SHINGLES", 4)
    selected = resolve_similarity(accel="required")
    right = "reference" + "abcd" * 100
    for index in range(8):
        left = f"candidate{index}" + "abcd" * 100
        assert selected(left, right) == 0.5
    first = "candidate0" + "abcd" * 100
    assert selected(first, right) == 0.5
    assert calls[first] == 2
    assert calls[right] == 1
    large_left, large_right = "abcd" * 1100, "bcde" * 1100
    assert selected(large_left, large_right) == 0.5
    assert selected(large_left, large_right) == 0.5
    assert calls[large_left] == 2
    assert calls[large_right] == 2
