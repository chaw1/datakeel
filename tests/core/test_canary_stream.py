# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Live output retains every possible sentinel prefix until it is known to be safe."""

import pytest

from datakeel.core.canary import HOLD_NON_WHITESPACE, CanaryStreamBuffer

CANARY = "dkc_0123456789abcdef01234567"
ANCESTOR = "dkc_fedcba0987654321fedcba09"


def test_normal_prose_streams_incrementally_and_flushes_exact_tail() -> None:
    """Preserve all original spacing while emitting before the response is complete."""
    chunks = ["The first useful sentence is ready. ", "Another sentence arrives. ", "Finished."]
    buffer = CanaryStreamBuffer([CANARY])
    emitted = [buffer.push(chunk) for chunk in chunks]
    assert all(emitted)
    assert "".join(emitted) != "".join(chunks)
    assert "".join(emitted) + buffer.finish() == "".join(chunks)
    assert buffer.finish() == ""
    assert buffer.emitted == sum(map(len, chunks))
    assert not buffer.leaked


def test_holdback_counts_non_whitespace_across_chunk_boundaries() -> None:
    """Arbitrarily large whitespace gaps cannot shrink the protected character window."""
    buffer = CanaryStreamBuffer([CANARY])
    protected = "a \n\t\u2003" * HOLD_NON_WHITESPACE
    assert buffer.push("") == ""
    assert buffer.push(protected[:25]) == ""
    assert buffer.push(protected[25:]) == ""
    assert buffer.push("b") == "a \n\t\u2003"
    assert buffer.finish() == protected[len("a \n\t\u2003") :] + "b"


@pytest.mark.parametrize("secret", [CANARY, ANCESTOR])
@pytest.mark.parametrize("fragment", [slice(None), slice(4, 20), slice(-16, None)])
@pytest.mark.parametrize("separator", ["", " \t\n\u2003"])
@pytest.mark.parametrize("chunk_size", [1, 7, 101])
def test_leaks_never_release_even_one_secret_character(
    secret: str, fragment: slice, separator: str, chunk_size: int
) -> None:
    """Catch full and partial mixed-case secrets even after safe text has streamed."""
    buffer = CanaryStreamBuffer(["", CANARY, ANCESTOR])
    prelude = "A useful answer starts with ordinary public words! " * 3
    emitted = buffer.push(prelude)
    assert emitted
    leaked = separator.join(secret[fragment].upper())
    for start in range(0, len(leaked), chunk_size):
        emitted += buffer.push(leaked[start : start + chunk_size])
        assert prelude.startswith(emitted)
    assert buffer.leaked
    assert buffer.push("Later output must also stay hidden.") == ""
    assert buffer.finish() == ""


@pytest.mark.parametrize("canaries", [(), ("",), (CANARY,)])
def test_clean_short_tail_and_subthreshold_fragment_flush(canaries: tuple[str, ...]) -> None:
    """Clean endings and fewer than sixteen random characters remain permitted."""
    buffer = CanaryStreamBuffer(canaries)
    text = " \n" + CANARY[4:19]
    assert buffer.push(text) == ""
    assert buffer.finish() == text
    assert not buffer.leaked


def test_whole_chunk_with_secret_is_rejected_before_any_release() -> None:
    """A malicious first chunk cannot emit a prefix before its leak check runs."""
    buffer = CanaryStreamBuffer([CANARY])
    assert buffer.push("Safe-looking prose. " * 10 + CANARY) == ""
    assert buffer.emitted == 0
    assert buffer.leaked
