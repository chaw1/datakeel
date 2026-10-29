# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check bounded candidate caches against an independent per-band query reference."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.llm_data_models import TrainingConfig
from datakeel.llm_data.index import DuplicateIndex

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path


class _CandidateIndex(DuplicateIndex):
    def populate(self) -> None:
        """Populate deterministic bands without depending on fingerprint bucket collisions."""
        for number in range(80):
            self._insert(
                f"record-{1000 - number}",
                str(number).encode(),
                f"normalized-{number}",
                number,
                tuple(bytes([band]) for band in range(8) if (number + band) % (band + 2) == 0),
                (f"prompt-{number}", f"answer-{number}"),
            )

    def append(self, number: int, bands: tuple[bytes, ...], text: str = "normalized") -> None:
        """Insert an immutable generated row through the production cache-refresh path."""
        self._insert(
            f"record-{number}", str(number).encode(), text, number, bands, ("prompt", "answer")
        )

    def candidates(self, keys: Sequence[bytes]) -> list[tuple[str, str, bytes, str, str]]:
        """Expose the candidate seam for an independent SQL reference comparison."""
        return self._candidates(keys)

    def cache_sizes(self) -> tuple[int, int]:
        """Expose entry counts without retaining or altering cached row payloads."""
        return len(self._bands), len(self._rows)


@pytest.fixture
def duplicate_index(tmp_path: Path) -> Iterator[_CandidateIndex]:
    """Populate sparse, overlapping and dense bands with deterministic record order."""
    index = _CandidateIndex(tmp_path / "index.sqlite", TrainingConfig())
    index.populate()
    try:
        yield index
    finally:
        index.close()


def _separate_query_reference(
    index: DuplicateIndex, keys: Sequence[bytes]
) -> list[tuple[str, str, bytes, str, str]]:
    identities: set[int] = set()
    for key in keys:
        identities.update(
            int(row[0])
            for row in index.connection.execute(
                "SELECT record_id FROM bands WHERE key=? ORDER BY record_id DESC LIMIT 8",
                (key,),
            )
        )
    if not identities:
        return []
    placeholders = ",".join("?" for _ in identities)
    query = (
        "SELECT record_id,normalized,simhash,prompt,answer FROM records WHERE id IN ("  # noqa: S608
        + placeholders
        + ") ORDER BY id"
    )
    return [
        (str(row[0]), str(row[1]), bytes(row[2]), str(row[3]), str(row[4]))
        for row in index.connection.execute(query, tuple(sorted(identities)))
    ]


def test_candidate_queries_preserve_each_band_limit_deduplication_and_record_order(
    duplicate_index: _CandidateIndex,
) -> None:
    """Dense, sparse, absent and repeated keys produce identical complete record tuples."""
    cases = [
        (),
        (b"absent",),
        (bytes([0]),),
        (bytes([7]),),
        (bytes([0]), bytes([0]), bytes([7]), b"absent"),
        tuple(bytes([band]) for band in range(8)),
        tuple(bytes([band]) for band in reversed(range(8))),
    ]
    for keys in cases:
        expected = _separate_query_reference(duplicate_index, keys)
        actual = duplicate_index.candidates(keys)
        assert actual == expected
        assert len(actual) <= 8 * len(set(keys))
    assert [row[0] for row in duplicate_index.candidates((bytes([0]),))] == [
        f"record-{1000 - number}" for number in range(64, 80, 2)
    ]


def test_candidate_cache_avoids_selects_for_warm_and_absent_bands(
    duplicate_index: _CandidateIndex,
) -> None:
    """Repeated candidates reuse bounded IDs and immutable rows without SQLite decoding."""
    keys = tuple(bytes([band]) for band in range(8))
    expected = _separate_query_reference(duplicate_index, keys)
    assert duplicate_index.candidates(keys) == expected
    assert duplicate_index.candidates((b"absent",)) == []
    statements: list[str] = []
    duplicate_index.connection.set_trace_callback(statements.append)
    assert duplicate_index.candidates(keys) == expected
    assert duplicate_index.candidates((b"absent",)) == []
    assert duplicate_index.candidates(()) == []
    assert statements == []


def test_candidate_cache_refreshes_recent_ids_after_new_records(
    duplicate_index: _CandidateIndex,
) -> None:
    """Insertions update cached dense bands and previously empty bands in reference order."""
    keys = (bytes([0]), b"new-band")
    duplicate_index.candidates(keys)
    for number in range(80, 92):
        duplicate_index.append(number, keys)
        assert duplicate_index.candidates(keys) == _separate_query_reference(duplicate_index, keys)
    assert [row[0] for row in duplicate_index.candidates(keys)] == [
        f"record-{number}" for number in range(84, 92)
    ]


def test_candidate_caches_evict_entries_and_preserve_disk_results(
    duplicate_index: _CandidateIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache growth stays bounded and evicted rows/bands reload without changing findings."""
    monkeypatch.setattr("datakeel.llm_data.index._MAX_CACHED_ROWS", 128)
    monkeypatch.setattr("datakeel.llm_data.index._MAX_CACHED_BANDS", 256)
    for number in range(1000, 1200):
        duplicate_index.append(number, (f"band-{number}".encode(),))
    assert duplicate_index.cache_sizes()[1] == 128
    for number in range(300):
        assert duplicate_index.candidates((f"absent-{number}".encode(),)) == []
    assert duplicate_index.cache_sizes()[0] == 256
    keys = (b"band-1000", b"band-1199")
    assert duplicate_index.candidates(keys) == _separate_query_reference(duplicate_index, keys)
    assert duplicate_index.cache_sizes() == (256, 128)


def test_candidate_cache_bypasses_oversized_rows_and_band_keys(
    duplicate_index: _CandidateIndex,
) -> None:
    """Bound retained bytes as well as row/key counts even for custom long input lines."""
    row_count = duplicate_index.cache_sizes()[1]
    duplicate_index.append(5000, (b"long-row",), "z" * 9000)
    assert duplicate_index.cache_sizes()[1] == row_count
    keys = (b"long-row",)
    expected = _separate_query_reference(duplicate_index, keys)
    assert duplicate_index.candidates(keys) == expected
    assert duplicate_index.cache_sizes()[1] == row_count
    statements: list[str] = []
    duplicate_index.connection.set_trace_callback(statements.append)
    assert duplicate_index.candidates(keys) == expected
    assert len(statements) == 1
    band_count = duplicate_index.cache_sizes()[0]
    assert duplicate_index.candidates((b"x" * 65,)) == []
    assert duplicate_index.cache_sizes()[0] == band_count
