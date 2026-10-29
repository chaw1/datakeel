# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read bounded JSONL lines and write deterministic, privacy-safe decision ledgers."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from pydantic import JsonValue

from datakeel.core.llm_data_models import TrainingRecord, TrainingSource


@dataclass(frozen=True)
class SourceLine:
    """Retain at most one configured line while hashing all bytes in oversized lines."""

    number: int
    raw: bytes
    digest: str
    oversized: bool


def source_lines(source: TrainingSource, limit: int) -> Iterator[SourceLine]:
    """Yield each physical line once without accumulating the file or an oversized record."""
    with Path(source.path).open("rb") as handle:
        number = 0
        while raw := handle.readline(limit + 1):
            number += 1
            line_hash = hashlib.sha256(raw)
            oversized = len(raw) > limit
            head = raw[:limit]
            while not raw.endswith(b"\n"):
                chunk = handle.readline(limit + 1)
                if not chunk:
                    break
                oversized = True
                line_hash.update(chunk)
                raw = chunk
            yield SourceLine(number, head, line_hash.hexdigest(), oversized)


def canonical_json(value: JsonValue) -> bytes:
    """Serialize deterministic UTF-8 JSONL bytes for reproducible fingerprints."""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


class DecisionWriter:
    """Stream complete decisions and cleaned payloads without retaining them in reports."""

    def __init__(self, ledger_path: Path | None, cleaned_dir: Path | None) -> None:
        """Open optional artifacts only at explicitly supplied local destinations."""
        self.ledger: BinaryIO | None = None
        if ledger_path is not None:
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            self.ledger = ledger_path.open("wb")
        if cleaned_dir is not None:
            cleaned_dir.mkdir(parents=True, exist_ok=True)
        self.cleaned_dir = cleaned_dir
        self.hasher = hashlib.sha256()
        self.output: BinaryIO | None = None

    def select(self, source: TrainingSource) -> None:
        """Close the previous output before selecting the next file, bounding open handles."""
        if self.output is not None:
            self.output.close()
        self.output = None
        if self.cleaned_dir is not None:
            # Source identities come from storage, but must never be interpreted as paths.
            self.output = (self.cleaned_dir / cleaned_filename(source.file_id)).open("wb")

    def write(self, record: TrainingRecord, payload: JsonValue | None) -> None:
        """Record all keeps/drops/redactions and emit retained records in original order."""
        encoded = (record.model_dump_json() + "\n").encode("utf-8")
        self.hasher.update(encoded)
        if self.ledger is not None:
            self.ledger.write(encoded)
        if self.output is not None and payload is not None and record.decision != "drop":
            self.output.write(canonical_json(payload))

    def close(self) -> None:
        """Close files on success and on parse or filesystem failures."""
        if self.ledger is not None:
            self.ledger.close()
        if self.output is not None:
            self.output.close()


def cleaned_filename(file_id: str) -> str:
    """Return a deterministic filename without interpreting source identities as paths."""
    return hashlib.sha256(file_id.encode()).hexdigest() + ".jsonl"
