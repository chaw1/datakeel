# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate every model sentence against only its explicitly cited platform facts."""

from pydantic import ValidationError

from datakeel.core.datasheet_models import (
    DATASHEET_CHAPTERS,
    DatasheetChapter,
    DatasheetDraft,
    DatasheetFact,
    DatasheetLanguage,
    DatasheetSection,
    DatasheetSentence,
    DatasheetValidation,
    DroppedSentence,
)
from datakeel.datasheets.matching import (
    atomic_sentences,
    numeric_issues,
    stable_unique,
    term_issues,
)
from datakeel.datasheets.vocabulary import chapter_title


def _reasons(
    sentence: DatasheetSentence, facts: tuple[DatasheetFact, ...], chapter: DatasheetChapter
) -> tuple[str, ...]:
    if not sentence.fact_ids:
        return ("missing_citation",)
    index = {fact.id: fact for fact in facts}
    if any(key not in index for key in sentence.fact_ids):
        return ("unknown_fact",)
    cited = tuple(index[key] for key in sentence.fact_ids)
    if not any(fact.chapter == chapter for fact in cited):
        return ("wrong_chapter",)
    return numeric_issues(sentence.text, cited) + term_issues(sentence.text, cited)


def validate_sections(
    sections: tuple[DatasheetSection, ...],
    facts: tuple[DatasheetFact, ...],
    language: DatasheetLanguage = "zh",
) -> DatasheetValidation:
    """Keep supported atomic sentences and record every rejected sentence explicitly."""
    kept: list[DatasheetSection] = []
    dropped: list[DroppedSentence] = []
    for key in DATASHEET_CHAPTERS:
        accepted: list[DatasheetSentence] = []
        for section in sections:
            if section.key != key:
                continue
            for candidate in section.sentences:
                for text in atomic_sentences(candidate.text):
                    sentence = DatasheetSentence(
                        text=text, fact_ids=stable_unique(candidate.fact_ids)
                    )
                    reasons = _reasons(sentence, facts, key)
                    if reasons:
                        dropped.append(DroppedSentence(**sentence.model_dump(), reasons=reasons))
                    else:
                        accepted.append(sentence)
        kept.append(
            DatasheetSection(
                key=key,
                title=chapter_title(key, language),
                sentences=tuple(accepted),
                missing=not any(fact.chapter == key for fact in facts),
            )
        )
    return DatasheetValidation(sections=tuple(kept), dropped_sentences=tuple(dropped))


def parse_model_output(
    text: str,
    facts: tuple[DatasheetFact, ...],
    language: DatasheetLanguage = "zh",
) -> DatasheetValidation:
    """Parse bounded JSON proposals without trusting model titles or missing flags."""
    try:
        draft = DatasheetDraft.model_validate_json(text)
    except ValidationError:
        checked = validate_sections((), facts, language)
        return checked.model_copy(
            update={"dropped_sentences": (DroppedSentence(text=text, reasons=("invalid_output",)),)}
        )
    return validate_sections(draft.sections, facts, language)
