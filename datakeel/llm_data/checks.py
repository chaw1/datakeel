# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply deterministic quality, privacy and preference-pair screening rules."""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from datakeel.core.llm_data_models import ParsedTrainingRecord, TrainingConfig, TrainingIssue
from datakeel.core.pii import detect_pii, redact_pii
from datakeel.llm_data.language import estimate_tokens
from datakeel.llm_data.parsing import issue

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pydantic import JsonValue

_HTML_URL = re.compile(r"</?[a-zA-Z][^>]*>|https?://\S+")
_MOJIBAKE = re.compile(r"\ufffd|[\x00-\x08\x0b\x0c\x0e-\x1f]|(?:Ã.|Â.|â€|锟斤拷)")
_WORDS = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]", re.IGNORECASE)
_FIELD_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_SCHEMA_KEYS = frozenset(
    {
        "messages",
        "role",
        "content",
        "tool_calls",
        "tool_call_id",
        "id",
        "type",
        "function",
        "name",
        "arguments",
        "tools",
        "parameters",
        "properties",
        "required",
        "description",
        "instruction",
        "input",
        "output",
        "prompt",
        "chosen",
        "rejected",
    }
)
_STRUCTURAL_VALUES = frozenset(
    {"", "user", "assistant", "system", "tool", "function", "text", "object", "string"}
)
_MIN_REPETITION_UNITS = 12
_MIN_PROMPT_LENGTH = 80
_MAX_GARBLED_RATIO = 0.01


def repetition_ratio(text: str) -> float:
    """Measure repeated token trigrams, including Chinese character trigrams."""
    tokens = _WORDS.findall(text.casefold())
    if len(tokens) < _MIN_REPETITION_UNITS:
        return 0
    grams = [tuple(tokens[index : index + 3]) for index in range(len(tokens) - 2)]
    return 1 - len(set(grams)) / len(grams)


def _privacy(
    value: JsonValue,
    field: str = "payload",
    label: str | None = None,
) -> Iterator[TrainingIssue]:
    if isinstance(value, str):
        if value in _STRUCTURAL_VALUES and (label is None or label in _SCHEMA_KEYS):
            return
        for match in detect_pii(value, label=label):
            yield TrainingIssue(
                code=f"pii_{match.type}",
                field=field,
                message=f"Detected {match.type}",
                evidence=match.placeholder,
                start=match.start,
                end=match.end,
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            private_key = key not in _SCHEMA_KEYS and bool(detect_pii(key))
            if private_key:
                yield from _privacy(key, f"{field}.[key]")
            label = key if not private_key and _FIELD_KEY.fullmatch(key) else "[field]"
            yield from _privacy(item, f"{field}.{label}", key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _privacy(item, f"{field}.{index}")


def _answer_findings(
    prompt: str, answer: str, field: str, config: TrainingConfig
) -> Iterator[TrainingIssue]:
    normalized = " ".join(answer.casefold().split())
    compact = re.sub(r"\s+", "", normalized)
    if any(
        phrase.casefold() in normalized or re.sub(r"\s+", "", phrase.casefold()) in compact
        for phrase in config.refusal_phrases
        if phrase
    ):
        yield issue("template_response", field, "Configured template phrase matched")
    if repetition_ratio(answer) >= config.repetition_threshold:
        yield issue("ngram_repetition", field, "High repeated trigram fraction")
    if answer.count("```") % 2:
        yield issue("unclosed_code_fence", field, "Unclosed fenced code block")
    if len(prompt) >= _MIN_PROMPT_LENGTH and len(answer.strip()) < len(prompt) * 0.03:
        yield issue("short_answer", field, "Answer is unusually short relative to prompt")


def _responses(value: JsonValue, field: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, list):
        for index, turn in enumerate(value):
            if not isinstance(turn, dict) or turn.get("role") != "assistant":
                continue
            content = turn.get("content")
            if isinstance(content, str):
                yield f"{field}.{index}.content", content
            elif isinstance(content, list):
                parts = [
                    block["text"]
                    for block in content
                    if isinstance(block, dict) and isinstance(block.get("text"), str)
                ]
                yield f"{field}.{index}.content", "\n".join(str(part) for part in parts)


def _quality_findings(
    record: ParsedTrainingRecord, config: TrainingConfig
) -> Iterator[TrainingIssue]:
    fields = (
        ("chosen", "rejected")
        if record.format == "preference"
        else (("messages",) if record.format == "messages" else ("output",))
    )
    for field in fields:
        for position, answer in _responses(record.payload.get(field), field):
            yield from _answer_findings(record.prompt, answer, position, config)


def check_record(record: ParsedTrainingRecord, config: TrainingConfig) -> tuple[TrainingIssue, ...]:
    """Return structural and measured heuristic signals with privacy-safe evidence."""
    findings = [*record.issues, *_privacy(record.payload), *_quality_findings(record, config)]
    if estimate_tokens(record.text) > config.max_tokens:
        findings.append(
            issue("token_limit", "text", "Estimated token count exceeds configured limit")
        )
    if len(_MOJIBAKE.findall(record.text)) / max(1, len(record.text)) > _MAX_GARBLED_RATIO:
        findings.append(
            issue("garbled_text", "text", "Control or replacement characters exceed 1%")
        )
    if _HTML_URL.search(record.text):
        findings.append(issue("html_url_residue", "text", "HTML markup or URL remains in text"))
    if any(term.casefold() in record.text.casefold() for term in config.safety_terms if term):
        findings.append(issue("safety_rule", "text", "Configured coarse screening term matched"))
    return tuple(findings)


def redact_payload(value: JsonValue, *, label: str | None = None) -> JsonValue:
    """Redact strings and labelled credential fields while preserving JSON structure."""
    if isinstance(value, str):
        return redact_pii(value, label=label)
    if isinstance(value, dict):
        output: dict[str, JsonValue] = {}
        for key, item in value.items():
            label = key if key in _SCHEMA_KEYS else redact_pii(key)
            while label in output:
                label += "[duplicate]"
            output[label] = redact_payload(item, label=key)
        return output
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    return value


def issue_counts(findings: tuple[TrainingIssue, ...]) -> Counter[str]:
    """Count affected records once per rule even if a record contains several matches."""
    return Counter({finding.code: 1 for finding in findings})
