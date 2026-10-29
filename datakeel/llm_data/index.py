# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Disk-backed exact, prompt and bounded LSH indexes avoid pairwise corpus scans."""

import sqlite3
from collections import OrderedDict
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from datakeel.core.llm_data_models import TrainingConfig, TrainingIssue
from datakeel.llm_data.acceleration import resolve_fingerprint, resolve_similarity
from datakeel.llm_data.similarity import digest, normalize
from datakeel.operators.evidence.near_duplicate_hashes import compare_hashes

_CANDIDATES_PER_BAND = 8
_MAX_CACHED_BANDS = 65536
_MAX_CACHED_BAND_BYTES = 64
_MAX_CACHED_ROWS = 16384
_MAX_CACHED_ROW_CHARACTERS = 8192
type _CandidateRow = tuple[str, str, bytes, str, str]


@lru_cache(maxsize=64)
def _record_query(count: int) -> str:
    # Only generated placeholders; record identities remain bound values.
    return (
        "SELECT id,record_id,normalized,simhash,prompt,answer FROM records WHERE id IN ("  # noqa: S608
        + ",".join(["?"] * count)
        + ")"
    )


class DuplicateIndex:
    """Keep corpus-sized indexes on disk and compare at most 64 candidates per new record."""

    def __init__(self, path: Path, config: TrainingConfig) -> None:
        """Create a disposable index with a fixed 16 MiB page cache."""
        self.config = config
        self.backend = "python"
        self.fingerprint = resolve_fingerprint()
        self.similarity = resolve_similarity()
        self._bands: OrderedDict[bytes, tuple[int, ...]] = OrderedDict()
        self._rows: OrderedDict[int, _CandidateRow] = OrderedDict()
        self.connection = sqlite3.connect(path)
        self.connection.executescript(
            "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA cache_size=-16384;"
            "CREATE TABLE records (id INTEGER PRIMARY KEY, digest BLOB UNIQUE, record_id TEXT,"
            " normalized TEXT, simhash BLOB, prompt TEXT, answer TEXT);"
            "CREATE TABLE bands (key BLOB, record_id INTEGER, "
            "PRIMARY KEY(key,record_id)) WITHOUT ROWID;"
            "CREATE TABLE prompts (digest BLOB PRIMARY KEY, answer BLOB, "
            "record_id TEXT) WITHOUT ROWID;"
        )

    def close(self) -> None:
        """Release the disposable index without requiring a durable transaction commit."""
        self.connection.close()
        self._bands.clear()
        self._rows.clear()

    def _band_ids(self, key: bytes) -> tuple[int, ...]:
        previous = self._bands.get(key)
        if previous is not None:
            self._bands.move_to_end(key)
            return previous
        identities = tuple(
            int(row[0])
            for row in self.connection.execute(
                "SELECT record_id FROM bands WHERE key=? ORDER BY record_id DESC LIMIT ?",
                (key, _CANDIDATES_PER_BAND),
            )
        )
        if len(key) <= _MAX_CACHED_BAND_BYTES:
            self._bands[key] = identities
            if len(self._bands) > _MAX_CACHED_BANDS:
                self._bands.popitem(last=False)
        return identities

    def _cache_row(self, identity: int, row: _CandidateRow) -> None:
        if sum(len(row[index]) for index in (0, 1, 3, 4)) > _MAX_CACHED_ROW_CHARACTERS:
            return
        self._rows[identity] = row
        if len(self._rows) > _MAX_CACHED_ROWS:
            self._rows.popitem(last=False)

    def _read_rows(self, identities: list[int]) -> dict[int, _CandidateRow]:
        rows: dict[int, _CandidateRow] = {}
        for values in self.connection.execute(_record_query(len(identities)), identities):
            identity = int(values[0])
            row = (str(values[1]), str(values[2]), bytes(values[3]), str(values[4]), str(values[5]))
            rows[identity] = row
            self._cache_row(identity, row)
        return rows

    def _candidates(self, keys: Sequence[bytes]) -> list[_CandidateRow]:
        identities = {identity for key in keys for identity in self._band_ids(key)}
        rows: dict[int, _CandidateRow] = {}
        missing: list[int] = []
        for identity in identities:
            row = self._rows.get(identity)
            if row is None:
                missing.append(identity)
            else:
                rows[identity] = row
                self._rows.move_to_end(identity)
        if missing:
            rows.update(self._read_rows(missing))
        return [rows[identity] for identity in sorted(rows)]

    def _near(
        self, normalized: str, hashed: int, keys: tuple[bytes, ...], prompt: str, answer: str
    ) -> TrainingIssue | None:
        for related_id, prior, prior_hash, prior_prompt, prior_answer in self._candidates(keys):
            distance = (hashed ^ int.from_bytes(prior_hash, "little")).bit_count()
            if distance > max(16, self.config.near_distance * 2):
                continue
            measured = self.similarity(normalized, prior)
            if measured < self.config.near_similarity:
                continue
            if (
                min(self.similarity(prompt, prior_prompt), self.similarity(answer, prior_answer))
                < self.config.near_similarity
            ):
                continue
            comparison = compare_hashes(
                (hashed, int.from_bytes(prior_hash, "little")),
                max(16, self.config.near_distance * 2),
                mode="exact",
            )
            self.backend = comparison.implementation
            if not comparison.pairs:
                continue
            distance = comparison.pairs[0][2]
            # MinHash candidates confirmed by textual similarity remain valid even if SimHash
            # differs on a short answer; SimHash supplies an independent distance measurement.
            return TrainingIssue(
                code="near_duplicate",
                message="MinHash candidate confirmed by normalized similarity",
                evidence=f"similarity={measured:.3f}; simhash_distance={distance}",
                related_id=related_id,
            )
        return None

    def check(
        self, record_id: str, text: str, prompt: str, answer: str, *, approximate: bool = True
    ) -> tuple[TrainingIssue, ...]:
        """Find a prior representative and retain unique records without expanding all pairs."""
        normalized = normalize(text)
        normalized_prompt = normalized if prompt == text else normalize(prompt)
        normalized_answer = normalized if answer == text else normalize(answer)
        key = digest(normalized)
        prior = self.connection.execute(
            "SELECT record_id FROM records WHERE digest=?", (key,)
        ).fetchone()
        findings: list[TrainingIssue] = []
        if prior:
            findings.append(
                TrainingIssue(
                    code="exact_duplicate",
                    message="Normalized record repeats a prior record",
                    related_id=str(prior[0]),
                )
            )
        else:
            hashed, keys = self.fingerprint(normalized) if approximate else (0, ())
            near = self._near(normalized, hashed, keys, normalized_prompt, normalized_answer)
            if near is not None:
                findings.append(near)
            else:
                self._insert(
                    record_id, key, normalized, hashed, keys, (normalized_prompt, normalized_answer)
                )
        conflict = self._prompt(record_id, normalized_prompt, normalized_answer)
        if conflict is not None:
            findings.append(conflict)
        return tuple(findings)

    def _insert(
        self,
        record_id: str,
        key: bytes,
        text: str,
        hashed: int,
        bands: tuple[bytes, ...],
        parts: tuple[str, str],
    ) -> None:
        hashed_bytes = hashed.to_bytes(8, "little")
        cursor = self.connection.execute(
            "INSERT INTO records(digest,record_id,normalized,simhash,prompt,answer) "
            "VALUES(?,?,?,?,?,?)",
            (key, record_id, text, hashed_bytes, *parts),
        )
        identity = cursor.lastrowid
        self.connection.executemany(
            "INSERT INTO bands VALUES(?,?)", ((band, identity) for band in bands)
        )
        if identity is not None:
            self._cache_row(identity, (record_id, text, hashed_bytes, *parts))
            for band in bands:
                previous = self._bands.get(band)
                if previous is not None:
                    self._bands[band] = (identity, *previous[: _CANDIDATES_PER_BAND - 1])

    def _prompt(self, record_id: str, prompt: str, answer: str) -> TrainingIssue | None:
        key, answer_key = digest(prompt), digest(answer)
        prior = self.connection.execute(
            "SELECT answer,record_id FROM prompts WHERE digest=?", (key,)
        ).fetchone()
        if prior is None:
            self.connection.execute(
                "INSERT INTO prompts VALUES(?,?,?)", (key, answer_key, record_id)
            )
        elif bytes(prior[0]) != answer_key:
            return TrainingIssue(
                code="prompt_conflict",
                field="prompt",
                message="Same prompt has different answers",
                related_id=str(prior[1]),
            )
        return None
