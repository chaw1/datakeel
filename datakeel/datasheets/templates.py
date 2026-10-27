# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline templates express recorded values without optional model dependencies."""

import json

from pydantic import JsonValue

from datakeel.core.datasheet_models import (
    DATASHEET_CHAPTERS,
    DatasheetFact,
    DatasheetLanguage,
    DatasheetSection,
    DatasheetSentence,
    DatasheetValidation,
)
from datakeel.datasheets.validation import validate_sections
from datakeel.datasheets.vocabulary import chapter_title, field_label

_EVENT_FIELDS = ("lineage.operator", "lineage.run_state", "lineage.occurred_at")
_PAIR = {"en": ": ", "zh": "\uff1a"}
_ENTRIES = {"en": ", ", "zh": "\uff0c"}
_ITEMS = {"en": ", ", "zh": "\u3001"}
_RECORDS = {"en": "; ", "zh": "\uff1b"}


def _scalar(value: JsonValue) -> str | None:
    if isinstance(value, dict | list):
        return None
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _member(record: dict[str, JsonValue], key: str) -> str | None:
    return _scalar(record[key]) if key in record else None


def _record(record: dict[str, JsonValue], language: DatasheetLanguage) -> str | None:
    # Issues read as their message and entities as "type: name"; other records keep scalars.
    message = _member(record, "message")
    if message is not None:
        message = message.rstrip(".。")
        dimension = _member(record, "dimension")
        if dimension is None or message.casefold().startswith(dimension.casefold()):
            return message
        return f"{dimension}{_PAIR[language]}{message}"
    name = _member(record, "name")
    if name is not None:
        # "type: name" keeps role words such as "team" from reading as a claim about the name.
        kind = _member(record, "type")
        return name if kind is None else f"{kind}{_PAIR[language]}{name}"
    members = tuple(
        f"{key}{_PAIR[language]}{text}"
        for key, item in record.items()
        if (text := _scalar(item)) is not None
    )
    return _ENTRIES[language].join(members) if members else None


def _list_text(values: list[JsonValue], language: DatasheetLanguage) -> str | None:
    scalars = tuple(_scalar(item) for item in values)
    if all(text is not None for text in scalars):
        return _ITEMS[language].join(text for text in scalars if text is not None)
    records = tuple(_record(item, language) if isinstance(item, dict) else None for item in values)
    if all(text is not None for text in records):
        return _RECORDS[language].join(text for text in records if text is not None)
    return None


def _entry(key: str, item: JsonValue, language: DatasheetLanguage) -> str | None:
    text = _scalar(item)
    if text is None and isinstance(item, list):
        text = _list_text(item, language)
    if text is None and isinstance(item, dict):
        # Scored dimensions read as their score; the complete breakdown stays in the fact.
        text = _member(item, "score")
        if text is None:
            record = _record(item, language)
            return None if record is None else f"{key} ({record})"
    return None if text is None else f"{key}{_PAIR[language]}{text}"


def _value_text(fact: DatasheetFact, language: DatasheetLanguage) -> str:
    value = fact.value
    text = _scalar(value)
    if text is None and value and isinstance(value, list):
        text = _list_text(value, language)
    if text is None and value and isinstance(value, dict):
        entries = tuple(_entry(key, item, language) for key, item in value.items())
        if all(entry is not None for entry in entries):
            flat = all(_scalar(item) is not None for item in value.values())
            separator = (_ENTRIES if flat else _RECORDS)[language]
            text = separator.join(entry for entry in entries if entry is not None)
    return json.dumps(value, ensure_ascii=False) if text is None else text


def fact_text(fact: DatasheetFact, language: DatasheetLanguage) -> str:
    """Present a recorded value with a localized factual label and readable punctuation."""
    return f"{field_label(fact.field, language)}{_PAIR[language]}{_value_text(fact, language)}"


def _literal_text(fact: DatasheetFact, language: DatasheetLanguage) -> str:
    value = json.dumps(fact.value, ensure_ascii=False)
    return f"{field_label(fact.field, language)}{_PAIR[language]}{value}"


def _fact_sentence(fact: DatasheetFact, language: DatasheetLanguage) -> DatasheetSentence:
    # Readable text must pass the same citation check alone, otherwise the literal value is used.
    readable = DatasheetSentence(text=fact_text(fact, language), fact_ids=(fact.id,))
    section = DatasheetSection(key=fact.chapter, title=fact.chapter, sentences=(readable,))
    if not validate_sections((section,), (fact,), language).dropped_sentences:
        return readable
    return DatasheetSentence(text=_literal_text(fact, language), fact_ids=(fact.id,))


def _event_sentences(
    facts: tuple[DatasheetFact, ...], language: DatasheetLanguage
) -> tuple[DatasheetSentence, ...]:
    # One processing step per sentence, in the order the platform recorded the steps.
    events: dict[str, list[DatasheetFact]] = {}
    for fact in facts:
        events.setdefault(fact.source_id, []).append(fact)
    ordered = sorted(
        events.values(), key=lambda group: (min(item.recorded_at for item in group), group[0].id)
    )
    separator = _RECORDS[language]
    sentences: list[DatasheetSentence] = []
    for group in ordered:
        group.sort(
            key=lambda item: (
                _EVENT_FIELDS.index(item.field) if item.field in _EVENT_FIELDS else 3,
                item.field,
            )
        )
        sentences.append(
            DatasheetSentence(
                text=separator.join(fact_text(item, language) for item in group),
                fact_ids=tuple(item.id for item in group),
            )
        )
    return tuple(sentences)


def _chapter_sentences(
    facts: tuple[DatasheetFact, ...], language: DatasheetLanguage
) -> tuple[DatasheetSentence, ...]:
    single = tuple(
        _fact_sentence(fact, language) for fact in facts if fact.source_type != "lineage_event"
    )
    events = tuple(fact for fact in facts if fact.source_type == "lineage_event")
    return single + _event_sentences(events, language)


def build_template(
    facts: tuple[DatasheetFact, ...], language: DatasheetLanguage = "zh"
) -> DatasheetValidation:
    """Generate all seven chapters with directly evidenced sentences for every fact."""
    sections: list[DatasheetSection] = []
    for key in DATASHEET_CHAPTERS:
        chapter = tuple(fact for fact in facts if fact.chapter == key)
        sentences = _chapter_sentences(chapter, language)
        sections.append(
            DatasheetSection(
                key=key,
                title=chapter_title(key, language),
                sentences=sentences,
                missing=not sentences,
            )
        )
    return validate_sections(tuple(sections), facts, language)
