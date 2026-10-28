# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Replayed label-based rewrites survive validation while every fabrication is removed."""

import pytest

from datakeel.core.datasheet_models import (
    DatasheetChapter,
    DatasheetSection,
    DatasheetSentence,
    DatasheetValidation,
)
from datakeel.datasheets.prompt import build_model_prompt, fact_display
from datakeel.datasheets.validation import validate_sections
from tests.datasheets.label_rewrite_cases import BAD, FACTS, LABELLED, UNLABELLED, Case


def _validate(chapter: str, text: str, keys: tuple[str, ...]) -> DatasheetValidation:
    key: DatasheetChapter = chapter  # type: ignore[assignment]  # Fixture chapters are literal.
    section = DatasheetSection(
        key=key,
        title=chapter,
        sentences=(DatasheetSentence(text=text, fact_ids=tuple(f"fact-{item}" for item in keys)),),
    )
    return validate_sections((section,), FACTS, "zh")


def _kept(cases: tuple[Case, ...]) -> int:
    return sum(not _validate(*case).dropped_sentences for case in cases)


@pytest.mark.parametrize("case", LABELLED, ids=[case[1] for case in LABELLED])
def test_label_based_rewrites_are_kept(case: Case) -> None:
    """Sentences that use the given label, unit and exact number wording are all retained."""
    assert _validate(*case).dropped_sentences == ()


@pytest.mark.parametrize("case", BAD, ids=[case[1] for case in BAD])
def test_fabrications_are_removed_with_their_reason(
    case: tuple[str, str, tuple[str, ...], str],
) -> None:
    """Percentages of counts, unit swaps, invented values and broken citations never survive."""
    chapter, text, keys, reason = case
    (dropped,) = _validate(chapter, text, keys).dropped_sentences
    assert reason in dropped.reasons


def test_labels_raise_retention_over_free_paraphrase() -> None:
    """The same true claims survive far more often when written with the provided labels."""
    labelled = _kept(LABELLED) / len(LABELLED)
    unlabelled = _kept(UNLABELLED) / len(UNLABELLED)
    assert labelled == 1
    assert unlabelled < 0.5


@pytest.mark.parametrize("language", ["zh", "en"])
def test_prompt_gives_each_fact_its_label_unit_and_display(language: str) -> None:
    """The model receives label, kind, unit and an exact-number display line for scalar facts."""
    prompt = build_model_prompt(FACTS, language)  # type: ignore[arg-type]  # Parametrized literal.
    for fact in FACTS:
        display = fact_display(fact, language)  # type: ignore[arg-type]
        assert (display is None) == isinstance(fact.value, dict | list)
        if display is not None:
            assert display in prompt
    assert "Copy every number exactly" in prompt
    assert "Only a fact of kind ratio may be restated as a percentage" in prompt
    assert ("文件数量=398 个" if language == "zh" else "File count=398 files") in prompt
