# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline templates express recorded values without optional model dependencies."""

import json

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


def _value_text(fact: DatasheetFact, language: DatasheetLanguage) -> str:
    value = fact.value
    if isinstance(value, str):
        return value
    if (
        isinstance(value, dict)
        and value
        and all(
            isinstance(item, int | float) and not isinstance(item, bool) for item in value.values()
        )
    ):
        # Count tables read as "key: value" pairs; nested or textual values stay as quoted JSON.
        pair, separator = (": ", ", ") if language == "en" else ("\uff1a", "\uff0c")
        return separator.join(f"{key}{pair}{item}" for key, item in value.items())
    return json.dumps(value, ensure_ascii=False)


def fact_text(fact: DatasheetFact, language: DatasheetLanguage) -> str:
    """Present a complete recorded value with a localized factual label."""
    separator = ": " if language == "en" else "\uff1a"
    return f"{field_label(fact.field, language)}{separator}{_value_text(fact, language)}"


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
    separator = "; " if language == "en" else "\uff1b"
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
        DatasheetSentence(text=fact_text(fact, language), fact_ids=(fact.id,))
        for fact in facts
        if fact.source_type != "lineage_event"
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
