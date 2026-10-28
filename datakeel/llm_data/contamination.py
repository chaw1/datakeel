# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Index only user-registered evaluation text and explain n-gram contamination hits."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, cast

from datakeel.core.llm_data_models import TrainingConfig, TrainingIssue, TrainingSource
from datakeel.llm_data.parsing import parse_record
from datakeel.llm_data.similarity import digest, normalize, similarity, tokens

if TYPE_CHECKING:
    from pydantic import JsonValue

_FUZZY_NGRAM = 4
_FUZZY_SIMILARITY = 0.88
_MAX_CANDIDATES = 32
_CHAR_NGRAM = 3


def _evaluation_text(raw: str) -> str:
    try:
        value = cast("JsonValue", json.loads(raw))
    except ValueError:
        return raw.strip()
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for field in ("question", "prompt", "text", "instruction"):
            candidate = value.get(field)
            if isinstance(candidate, str):
                return candidate
        try:
            return parse_record(raw).prompt
        except (ValueError, TypeError):
            return ""
    return ""


def _grams(parts: tuple[str, ...], size: int) -> set[bytes]:
    return {
        digest("\x1f".join(parts[offset : offset + size]))
        for offset in range(max(0, len(parts) - size + 1))
    }


def _character_grams(text: str) -> set[bytes]:
    normalized = normalize(text)
    size = min(_CHAR_NGRAM, len(normalized))
    return (
        {
            b"c" + digest(normalized[offset : offset + size])
            for offset in range(max(0, len(normalized) - size + 1))
        }
        if size
        else set()
    )


def evaluation_lines(source: TrainingSource, limit: int) -> Iterator[tuple[int, bytes]]:
    """Stream evaluation lines, discarding oversized entries without loading the file."""
    with Path(source.path).open("rb") as handle:
        line = 0
        while raw := handle.readline(limit + 1):
            line += 1
            oversized = len(raw) > limit
            while not raw.endswith(b"\n"):
                chunk = handle.readline(limit + 1)
                if not chunk:
                    break
                oversized = True
                raw = chunk
            if not oversized:
                yield line, raw


class ContaminationIndex:
    """Use a disk inverted n-gram index; adding evaluation data is linear in its length."""

    def __init__(self, path: Path, config: TrainingConfig) -> None:
        """Create bounded-cache disposable tables, separate from authoritative storage."""
        self.config = config
        self.count = 0
        self.connection = sqlite3.connect(path)
        self.connection.executescript(
            "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA cache_size=-8192;"
            "CREATE TABLE docs (id INTEGER PRIMARY KEY, ref TEXT, text TEXT, grams INTEGER);"
            "CREATE TABLE grams (hash BLOB, doc INTEGER, PRIMARY KEY(hash,doc)) WITHOUT ROWID;"
        )

    def close(self) -> None:
        """Release the ephemeral evaluation index."""
        self.connection.close()

    def register(self, sources: tuple[TrainingSource, ...]) -> dict[str, str]:
        """Register generated or user-owned JSONL/text, never packaged benchmark questions."""
        hashes: dict[str, str] = {}
        for source in sources:
            with Path(source.path).open("rb") as handle:
                hashes[source.file_id] = hashlib.file_digest(handle, "sha256").hexdigest()
            for line, raw in evaluation_lines(source, self.config.max_line_bytes):
                text = _evaluation_text(raw.decode("utf-8", errors="replace"))
                parts = tokens(text)
                if not parts:
                    continue
                main = _grams(parts, self.config.contamination_ngram)
                fuzzy = _grams(parts, min(_FUZZY_NGRAM, len(parts)))
                cursor = self.connection.execute(
                    "INSERT INTO docs(ref,text,grams) VALUES(?,?,?)",
                    (f"{source.file_id}:{line}", text, len(main)),
                )
                self.connection.executemany(
                    "INSERT INTO grams VALUES(?,?)",
                    ((key, cursor.lastrowid) for key in main | fuzzy | _character_grams(text)),
                )
                self.count += 1
        return hashes

    def check(self, text: str) -> tuple[TrainingIssue, ...]:
        """Retrieve candidate references and verify overlap or conservative fuzzy agreement."""
        if not self.count:
            return ()
        parts = tokens(text)
        main = _grams(parts, self.config.contamination_ngram)
        fuzzy = _grams(parts, min(_FUZZY_NGRAM, len(parts)))
        candidates: set[int] = set()
        for key in main | fuzzy | _character_grams(text):
            candidates.update(
                int(row[0])
                for row in self.connection.execute(
                    "SELECT doc FROM grams WHERE hash=? LIMIT ?",
                    (key, _MAX_CANDIDATES),
                )
            )
        findings: list[TrainingIssue] = []
        for identity in sorted(candidates):
            row = self.connection.execute(
                "SELECT ref,text,grams FROM docs WHERE id=?", (identity,)
            ).fetchone()
            if row is not None:
                finding = self._verify(text, main, str(row[0]), str(row[1]))
                if finding is not None:
                    findings.append(finding)
        return tuple(findings[: self.config.sample_limit or 1])

    def _verify(
        self, text: str, main: set[bytes], ref: str, evaluation: str
    ) -> TrainingIssue | None:
        evaluation_parts = tokens(evaluation)
        reference = _grams(evaluation_parts, self.config.contamination_ngram)
        overlap = len(reference & main) / max(1, len(reference))
        exact = bool(reference) and overlap >= self.config.contamination_threshold
        normalized, expected = normalize(text), normalize(evaluation)
        contained = bool(expected) and (
            expected == normalized
            or (len(evaluation_parts) >= _FUZZY_NGRAM and expected in normalized)
        )
        fuzzy = (
            len(evaluation_parts) >= _FUZZY_NGRAM
            and similarity(normalized, expected) >= _FUZZY_SIMILARITY
        )
        if not (exact or contained or fuzzy):
            return None
        return TrainingIssue(
            code="contamination",
            field="prompt",
            message="User-registered evaluation entry matched",
            evidence=f"n-gram coverage={overlap:.3f}; n={self.config.contamination_ngram}",
            related_id=ref,
        )
