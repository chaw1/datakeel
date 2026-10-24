# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pluggable typed extraction with deterministic offline implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ProviderError
from datakeel.core.harness_models import TokenUsage
from datakeel.core.kg_errors import ExtractionProviderError, KGExtractionError
from datakeel.core.kg_models import ExtractionResult, RawExtraction, Recording
from datakeel.kg.loader import load_contract

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.kg_contracts import KGSchema
    from datakeel.core.kg_models import TextBlock


class ExtractorAdapter(Protocol):
    """Extract one offset-preserving text block using a checked vocabulary."""

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        """Return raw claims and finish status without filtering ungrounded relations."""
        ...


class FakeExtractor:
    """Consume explicit scripted outputs without network or model dependencies."""

    def __init__(self, results: tuple[ExtractionResult | str, ...] = ()) -> None:
        """Accept result values or safe error categories for deterministic tests."""
        self.results = results
        self.calls = 0

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        """Advance the script, returning an empty extraction when no script remains."""
        del block, schema
        index = self.calls
        self.calls += 1
        result = (
            self.results[index]
            if index < len(self.results)
            else ExtractionResult(output=RawExtraction())
        )
        if isinstance(result, str):
            raise KGExtractionError(result)
        return result


class ReplayExtractor:
    """Look up attributable recorded model output by the exact block content hash."""

    def __init__(self, recording: Recording) -> None:
        """Validate recording identities before replay begins."""
        self.recording = recording
        self.records = {record.text_hash: record for record in recording.records}
        self.calls = 0

    @classmethod
    def from_path(cls, path: Path) -> ReplayExtractor:
        """Load one recording without accessing any remote model endpoint."""
        return cls(load_contract(path, Recording))

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        """Return the recorded output or a visible missing-record failure."""
        del schema
        self.calls += 1
        record = self.records.get(block.content_hash)
        if record is None:
            reason = "replay_missing"
            raise KGExtractionError(reason)
        return ExtractionResult(
            output=record.output,
            finish_reason=record.finish_reason,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cache_read_tokens=record.cache_read_tokens,
            cache_write_tokens=record.cache_write_tokens,
            ignored_top_level_keys=record.ignored_top_level_keys,
        )


def checked_extract(
    adapter: ExtractorAdapter, block: TextBlock, schema: KGSchema
) -> ExtractionResult:
    """Reject truncation and parse failures before callers write a successful cache entry."""
    try:
        result = adapter.extract(block, schema)
    except ExtractionProviderError as error:
        raise KGExtractionError(error.reason, observed_usage=error.observed_usage) from error
    except ProviderError as error:
        raise KGExtractionError(error.reason) from error
    except ModelValidationError as error:
        reason = "parse_failure"
        raise KGExtractionError(reason) from error
    if result.finish_reason in {"length", "max_tokens"}:
        reason = "truncated"
        observed = (
            TokenUsage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_read_tokens=result.cache_read_tokens,
                cache_write_tokens=result.cache_write_tokens,
            )
            if result.input_tokens is not None and result.output_tokens is not None
            else None
        )
        raise KGExtractionError(reason, observed_usage=observed)
    return result
