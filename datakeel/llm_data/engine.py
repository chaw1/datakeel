# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stream training records into deterministic summaries, dry runs and clean outputs."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Literal

from datakeel.core.llm_data_models import (
    ParsedTrainingRecord,
    TrainingConfig,
    TrainingFileSummary,
    TrainingIssue,
    TrainingRecord,
    TrainingReport,
    TrainingSource,
)
from datakeel.core.pii import redact_pii
from datakeel.llm_data.checks import check_record, issue_counts, redact_payload
from datakeel.llm_data.contamination import ContaminationIndex
from datakeel.llm_data.index import DuplicateIndex
from datakeel.llm_data.language import estimate_tokens, identify_language
from datakeel.llm_data.parsing import parse_record
from datakeel.llm_data.similarity import normalize, similarity
from datakeel.llm_data.streaming import DecisionWriter, SourceLine, source_lines

if TYPE_CHECKING:
    from pydantic import JsonValue

_BLOCKING = frozenset(
    {
        "format_error",
        "line_too_large",
        "role_order",
        "missing_final_assistant",
        "empty_turn",
        "empty_prompt",
        "token_limit",
        "unclosed_code_fence",
        "exact_duplicate",
        "near_duplicate",
        "chosen_empty",
        "preference_identical",
        "preference_near_identical",
        "preference_prompt_mismatch",
        "contamination",
    }
)
_PREVIEW_LIMIT = 1200


@dataclass
class _Summary:
    config: TrainingConfig
    counts: Counter[str] = field(default_factory=Counter[str])
    languages: Counter[str] = field(default_factory=Counter[str])
    formats: Counter[str] = field(default_factory=Counter[str])
    decisions: Counter[str] = field(default_factory=Counter[str])
    files: list[TrainingFileSummary] = field(default_factory=list[TrainingFileSummary])
    samples: list[TrainingRecord] = field(default_factory=list[TrainingRecord])
    clusters: list[tuple[str, ...]] = field(default_factory=list[tuple[str, ...]])
    contamination: list[TrainingIssue] = field(default_factory=list[TrainingIssue])
    records: int = 0
    valid: int = 0
    preferences: int = 0
    chosen_longer: int = 0
    pii_records: int = 0

    def add(self, record: TrainingRecord, parsed: ParsedTrainingRecord | None) -> None:
        self.records += 1
        if record.issues:
            self.counts.update(issue_counts(record.issues))
        self.decisions[record.decision] += 1
        self.pii_records += any(item.code.startswith("pii_") for item in record.issues)
        if parsed is not None:
            self.valid += 1
            self.languages[record.language] += 1
            self.formats[record.format] += 1
            if parsed.format == "preference":
                self.preferences += 1
                self.chosen_longer += len(parsed.answer) > len(parsed.rejected)
        limit = self.config.sample_limit
        if len(self.samples) < limit:
            self.samples.append(record)
        elif record.issues and limit and not self.samples[-1].issues:
            self.samples[-1] = record
        for finding in record.issues:
            if finding.code in {"exact_duplicate", "near_duplicate"} and len(self.clusters) < limit:
                self.clusters.append((finding.related_id or "", record.id))
            if finding.code == "contamination" and len(self.contamination) < limit:
                self.contamination.append(finding.model_copy(update={"field": record.id}))

    def report(self, writer: DecisionWriter, index: DuplicateIndex) -> TrainingReport:
        return TrainingReport(
            config=self.config,
            records=self.records,
            valid_records=self.valid,
            issue_counts=dict(sorted(self.counts.items())),
            languages=dict(sorted(self.languages.items())),
            formats=dict(sorted(self.formats.items())),
            files=tuple(self.files),
            samples=tuple(self.samples),
            duplicate_clusters=tuple(self.clusters),
            contamination_hits=tuple(self.contamination),
            preference_records=self.preferences,
            chosen_longer_ratio=self.chosen_longer / max(1, self.preferences),
            dropped=self.decisions["drop"],
            redacted=self.decisions["redact"],
            kept=self.decisions["keep"],
            pii_records=self.pii_records,
            ledger_sha256=writer.hasher.hexdigest(),
            dedup_backend=index.backend,
        )


def _preference_findings(
    parsed: ParsedTrainingRecord, config: TrainingConfig
) -> list[TrainingIssue]:
    if parsed.format != "preference":
        return []
    chosen, rejected = normalize(parsed.answer), normalize(parsed.rejected)
    code = "preference_identical" if chosen == rejected else "preference_near_identical"
    if chosen != rejected and similarity(chosen, rejected) < config.near_similarity:
        return []
    return [
        TrainingIssue(
            code=code,
            field="chosen/rejected",
            message="Preference answers have no meaningful distinction",
        )
    ]


def _decision(findings: tuple[TrainingIssue, ...]) -> Literal["keep", "drop", "redact"]:
    if not findings:
        return "keep"
    codes = {finding.code for finding in findings}
    if codes & _BLOCKING:
        return "drop"
    return "redact" if any(code.startswith("pii_") for code in codes) else "keep"


def _invalid(
    source: TrainingSource, line: SourceLine, config: TrainingConfig, message: str
) -> TrainingRecord:
    code = "line_too_large" if line.oversized else "format_error"
    return TrainingRecord(
        id=f"{source.file_id}:{line.number}:{line.digest[:16]}",
        file_id=source.file_id,
        line=line.number,
        content_hash=line.digest,
        format=config.format,
        preview="[UNPARSEABLE_RECORD]",
        issues=(TrainingIssue(code=code, message=message),),
        decision="drop",
        reasons=(code,),
    )


def _inspect(
    source: TrainingSource,
    line: SourceLine,
    config: TrainingConfig,
    index: DuplicateIndex,
    contamination: ContaminationIndex,
) -> tuple[TrainingRecord, ParsedTrainingRecord | None]:
    if line.oversized:
        return _invalid(source, line, config, "Line exceeds the configured byte limit"), None
    try:
        parsed = parse_record(line.raw.decode("utf-8-sig"), config.format)
    except UnicodeDecodeError as error:
        message = f"Invalid UTF-8 at byte {error.start}"
        return _invalid(source, line, config, message), None
    except json.JSONDecodeError as error:
        message = f"Invalid JSON: {error.msg} at column {error.colno}"
        return _invalid(source, line, config, message), None
    except (ValueError, TypeError) as error:
        return _invalid(source, line, config, str(error)), None
    except RecursionError:
        return _invalid(source, line, config, "JSON nesting exceeds the safe parser limit"), None
    identity = f"{source.file_id}:{line.number}:{line.digest[:16]}"
    tokens = estimate_tokens(parsed.text)
    base_findings = (
        *check_record(parsed, config, estimated_tokens=tokens),
        *_preference_findings(parsed, config),
    )
    duplicate_findings = (
        index.check(identity, parsed.text, parsed.prompt, parsed.answer)
        if not {finding.code for finding in base_findings} & _BLOCKING
        else ()
    )
    findings = (
        *base_findings,
        *duplicate_findings,
        *contamination.check(parsed.prompt),
        *contamination.check(parsed.answer),
    )
    language, confidence = identify_language(parsed.text)
    preview = (
        redact_pii(parsed.text)
        if any(finding.code.startswith("pii_") for finding in findings)
        else parsed.text
    )
    return TrainingRecord(
        id=identity,
        file_id=source.file_id,
        line=line.number,
        content_hash=line.digest,
        format=parsed.format,
        language=language,
        language_confidence=confidence,
        estimated_tokens=tokens,
        preview=preview[:_PREVIEW_LIMIT],
        issues=findings,
        decision=_decision(findings),
        reasons=tuple(sorted({item.code for item in findings})) or ("no_blocking_findings",),
    ), parsed


def _scan(
    sources: tuple[TrainingSource, ...],
    summary: _Summary,
    index: DuplicateIndex,
    contamination: ContaminationIndex,
    writer: DecisionWriter,
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for source in sources:
        counts: Counter[str] = Counter()
        valid, records = 0, 0
        writer.select(source)
        with Path(source.path).open("rb") as handle:
            hashes[source.file_id] = hashlib.file_digest(handle, "sha256").hexdigest()
        for line in source_lines(source, summary.config.max_line_bytes):
            record, parsed = _inspect(source, line, summary.config, index, contamination)
            summary.add(record, parsed)
            records += 1
            valid += parsed is not None
            if record.issues:
                counts.update(issue_counts(record.issues))
            payload: JsonValue | None = parsed.payload if parsed is not None else None
            if record.decision == "redact":
                payload = redact_payload(payload)
            writer.write(record, payload)
        summary.files.append(
            TrainingFileSummary(
                file_id=source.file_id,
                filename=source.filename,
                records=records,
                valid_records=valid,
                issue_counts=dict(sorted(counts.items())),
            )
        )
    return hashes


def analyze_sources(
    sources: tuple[TrainingSource, ...],
    config: TrainingConfig | None = None,
    *,
    evaluations: tuple[TrainingSource, ...] = (),
    ledger_path: Path | None = None,
    cleaned_dir: Path | None = None,
) -> TrainingReport:
    """Run all offline checks with fixed-memory indexes and reproducible streamed artifacts.

    Source order is part of the frozen configuration: the first retained duplicate is
    the representative. No content is sent to a model, network service or telemetry.
    """
    resolved = config or TrainingConfig()
    summary = _Summary(resolved)
    with TemporaryDirectory(prefix="datakeel-training-") as temporary:
        index = DuplicateIndex(Path(temporary) / "duplicates.sqlite", resolved)
        contamination = ContaminationIndex(Path(temporary) / "evaluation.sqlite", resolved)
        writer = DecisionWriter(ledger_path, cleaned_dir)
        try:
            evaluation_hashes = contamination.register(evaluations)
            source_hashes = _scan(sources, summary, index, contamination, writer)
            return summary.report(writer, index).model_copy(
                update={
                    "source_sha256": source_hashes,
                    "evaluation_sha256": evaluation_hashes,
                }
            )
        finally:
            writer.close()
            index.close()
            contamination.close()
