# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Citation validation refuses invented numbers, names and unbound references."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import JsonValue

from datakeel.core.datasheet_models import (
    DatasheetFact,
    DatasheetSection,
    DatasheetSentence,
    DatasheetValidation,
)
from datakeel.datasheets.validation import parse_model_output, validate_sections


def fact(value: JsonValue, *, key: str = "f1") -> DatasheetFact:
    """Create independent frozen evidence without external stores or model calls."""
    return DatasheetFact(
        id=key,
        chapter="composition",
        source_type="manifest",
        source_id="source-9999",
        field="manifest.file_count",
        value=value,
        recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
    )


def checked(
    text: str, values: tuple[DatasheetFact, ...], ids: tuple[str, ...] = ("f1",)
) -> DatasheetValidation:
    """Verify one proposed sentence through the public seven-chapter boundary."""
    return validate_sections(
        (
            DatasheetSection(
                key="composition",
                title="Untrusted title",
                sentences=(DatasheetSentence(text=text, fact_ids=ids),),
            ),
        ),
        values,
    )


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("The dataset contains 1,234 files.", 1234),
        ("The dataset contains \uff11\uff12\uff13\uff14 files.", 1234),
        ("The quality score is 98.3%.", 0.983),
        ("The quality score is 0.983.", "98.3%"),
        ("The quality score is -1.25.", -1.25),
        ("The quality score is 1.2e3.", 1200),
        ("Collection date: 2026/01/02.", "2026-01-02"),
        ("采集日期为2026年1月2日。", "2026-01-02"),
        ("The dataset is maintained by Cedar Unit.", "Cedar Unit"),
        (
            "Cedar Unit maintains AtlasBoard.",
            {"owner": "Cedar Unit", "name": "AtlasBoard", "role": "maintains"},
        ),
        ("该数据集由星河团队维护。", "星河团队"),
        ("The owner is Élodie.", "E\u0301lodie"),
        ("File names: data_1.csv.", ["data_1.csv"]),
        ("The data contains true and null.", [True, None]),
        ("The quality score is 98.3%.", 98.3),
        ("The version was created on 2026-10-27.", "2026-10-27T14:30:17+00:00"),
        ("The version was created on October 27, 2026.", "2026-10-27T14:30:17+00:00"),
    ],
)
def test_supported_sentence_keeps_normalized_values(text: str, value: JsonValue) -> None:
    """Equivalent numeric forms and recorded names survive the independent checker."""
    result = checked(text, (fact(value),))
    assert result.dropped_sentences == ()
    assert len(result.sections[1].sentences) == 1


@pytest.mark.parametrize(
    ("text", "values", "reason"),
    [
        ("The dataset contains 1235 files.", (fact(1234),), "unsupported_number"),
        ("The dataset contains 9999 files.", (fact(1234),), "unsupported_number"),
        ("The quality score is 98.3.", (fact(0.983),), "unsupported_number"),
        ("The quality score is 99%.", (fact(98.3),), "unsupported_number"),
        ("The dataset contains 12% images.", (fact(1200),), "unsupported_number"),
        ("Northstar created the dataset.", (fact("Cedar Unit"),), "unsupported_term"),
        ("The dataset was created by Northstar.", (fact("Cedar Unit"),), "unsupported_term"),
        ("Collection date: 2027-01-02.", (fact("2026-01-02"),), "unsupported_date"),
        ("Northstar owns the dataset.", (fact("Cedar Unit"),), "unsupported_term"),
        ("The owner is northstar.", (fact("Cedar Unit"),), "unsupported_term"),
        ("该数据集由王小明维护。", (fact("星河团队"),), "unsupported_term"),
        ("该数据集由北京大学维护。", (fact(["北京", "大学"]),), "unsupported_term"),
        (
            "AtlasBoard Unit is the owner.",
            (fact(["Cedar Unit", "AtlasBoard"]),),
            "unsupported_term",
        ),
        (
            "The dataset contains 4321 files.",
            (fact(1234), fact(4321, key="uncited")),
            "unsupported_number",
        ),
        (
            "Northstar is the owner.",
            (fact("Cedar Unit"), fact("Northstar", key="uncited")),
            "unsupported_term",
        ),
    ],
)
def test_unsupported_sentence_is_removed_with_reason(
    text: str, values: tuple[DatasheetFact, ...], reason: str
) -> None:
    """Uncited facts and incidental source identities never justify a generated claim."""
    result = checked(text, values)
    assert result.sections[1].sentences == ()
    assert reason in result.dropped_sentences[0].reasons


def test_unknown_reference_is_removed_and_recorded() -> None:
    """A model cannot cite an invented fact even when text resembles a recorded value."""
    result = checked("The dataset contains 12 files.", (fact(12),), ("invented",))
    assert result.sections[1].sentences == ()
    assert result.dropped_sentences[0].reasons == ("unknown_fact",)


def test_missing_reference_is_removed_and_recorded() -> None:
    """An uncited sentence cannot enter a datasheet even when numerically correct."""
    result = checked("The dataset contains 12 files.", (fact(12),), ())
    assert result.sections[1].sentences == ()
    assert result.dropped_sentences[0].reasons == ("missing_citation",)


def test_compound_entry_validates_each_atomic_sentence() -> None:
    """A good opening sentence cannot conceal a fabricated second statement."""
    result = checked("The dataset contains 12 files. The owner is Northstar.", (fact(12),))
    assert len(result.sections[1].sentences) == 1
    assert len(result.dropped_sentences) == 1
    assert "Northstar" in result.dropped_sentences[0].text


def test_replay_output_retains_good_sentence_and_records_all_four_failures() -> None:
    """Strict JSON replay exposes the full four-way failure ledger required for review."""
    sentences: list[dict[str, JsonValue]] = [
        {"text": "The dataset contains 12 files.", "fact_ids": ["f1"]},
        {"text": "The dataset contains 13 files.", "fact_ids": ["f1"]},
        {"text": "The owner is Northstar.", "fact_ids": ["f1"]},
        {"text": "The dataset contains 12 files.", "fact_ids": ["missing"]},
        {"text": "The dataset contains 12 files.", "fact_ids": []},
    ]
    raw = json.dumps(
        {"sections": [{"key": "composition", "title": "Injected", "sentences": sentences}]}
    )
    result = parse_model_output(raw, (fact(12),), "en")
    assert len(result.sections) == 7
    assert result.sections[1].title == "Composition"
    assert len(result.sections[1].sentences) == 1
    assert {reason for item in result.dropped_sentences for reason in item.reasons} == {
        "unsupported_number",
        "unsupported_term",
        "unknown_fact",
        "missing_citation",
    }


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"sections": [], "instruction": "ignore checks"}',
        '{"sections": [{"key": "invented"}]}',
    ],
)
def test_malformed_model_output_is_an_explicit_rejection(raw: str) -> None:
    """Malformed proposals become reviewable rejections rather than unvalidated prose."""
    result = parse_model_output(raw, ())
    assert len(result.sections) == 7
    assert all(section.missing for section in result.sections)
    assert result.dropped_sentences[0].reasons == ("invalid_output",)


def test_duplicate_fact_references_are_normalized() -> None:
    """Duplicate citations do not duplicate evidence in exports or verification."""
    result = checked("The dataset contains 12 files.", (fact(12),), ("f1", "f1"))
    assert result.sections[1].sentences[0].fact_ids == ("f1",)


def test_missing_chapter_cannot_borrow_a_sentence_from_another_chapter() -> None:
    """Absence labels and retained prose cannot contradict one another."""
    candidate = DatasheetSection(
        key="maintenance",
        title="Maintenance",
        sentences=(DatasheetSentence(text="The dataset contains 12 files.", fact_ids=("f1",)),),
    )
    result = validate_sections((candidate,), (fact(12),))
    assert result.sections[6].missing
    assert result.sections[6].sentences == ()
    assert result.dropped_sentences[0].reasons == ("wrong_chapter",)


def test_previously_unseen_lowercase_name_cannot_be_assembled_from_recorded_parts() -> None:
    """Lowercasing an invented multiword identity does not bypass whole-phrase support."""
    result = checked("atlasboard unit is the owner.", (fact(["Cedar Unit", "AtlasBoard"]),))
    assert result.sections[1].sentences == ()
    assert result.dropped_sentences[0].reasons == ("unsupported_term",)


@pytest.mark.parametrize(
    "text",
    [
        "数据集包含999个文件。",
        "数据集包含九百九十九个文件。",
        "数据集包含三张图片。",
        "The dataset contains one file.",
    ],
)
def test_written_or_unspaced_numbers_cannot_bypass_support_checks(text: str) -> None:
    """Han letters adjacent to Arabic digits and written numerals remain untrusted."""
    result = checked(text, (fact(12),))
    assert result.sections[1].sentences == ()
    assert result.dropped_sentences


def test_supported_unspaced_chinese_number_survives() -> None:
    """Chinese prose uses the same exact numeric support as spaced English prose."""
    result = checked("数据集包含12个文件。", (fact(12),))
    assert len(result.sections[1].sentences) == 1
    assert result.dropped_sentences == ()


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("The dataset contains twelve files.", 12),
        ("The dataset contains one hundred and twenty-three files.", 123),
        ("数据集包含三张图片。", 3),
        ("数据集包含九百九十九个文件。", 999),
        ("The quality score is 98.3 percent.", 0.983),
    ],
)
def test_written_number_matches_only_its_numeric_value(text: str, value: JsonValue) -> None:
    """Cardinals are numbers rather than ordinary grammar or generic proper-name tokens."""
    result = checked(text, (fact(value),))
    assert result.dropped_sentences == ()
    assert len(result.sections[1].sentences) == 1


def test_chinese_numeral_substring_cannot_invent_a_smaller_count() -> None:
    """The character three inside thirteen is not numeric evidence for three files."""
    result = checked("数据集包含三张图片。", (fact("十三"),))
    assert "unsupported_number" in result.dropped_sentences[0].reasons


@pytest.mark.parametrize(
    "date_text", ["January 2, 2026", "Jan. 2 2026", "2 January 2026", "2 Jan 2026"]
)
def test_named_dates_match_a_cited_iso_date(date_text: str) -> None:
    """Common model date spellings remain equivalent without admitting an unsupported date."""
    result = checked(f"Collection date: {date_text}.", (fact("2026-01-02"),))
    assert result.dropped_sentences == ()
    assert len(result.sections[1].sentences) == 1


@pytest.mark.parametrize(
    ("date_text", "reasons"),
    [
        ("2026 年 1 月 2 日", ()),
        ("2026年 1月 2日", ()),
        ("2026 年 01 月 02 日", ()),
        ("2026 年 1 月 3 日", ("unsupported_date",)),
        ("2025 年 1 月 2 日", ("unsupported_date",)),
    ],
)
def test_spaced_chinese_dates_are_compared_as_calendar_days(
    date_text: str, reasons: tuple[str, ...]
) -> None:
    """Spaces around 年/月/日 neither delete a supported date nor hide an invented one."""
    result = checked(f"采集日期为{date_text}。", (fact("2026-01-02"),))
    assert tuple(reason for item in result.dropped_sentences for reason in item.reasons) == reasons


@pytest.mark.parametrize(
    ("text", "value", "kept"),
    [
        (
            "质量问题包括consistency_below_target和annotation_excluded。",
            [{"code": "consistency_below_target"}, {"code": "annotation_excluded"}],
            True,
        ),
        ("负责人为 Cedar Unit 和 Acorn Unit。", ["Cedar Unit", "Acorn Unit"], True),
        ("文件包括 north.png 与 south.png。", ["north.png", "south.png"], True),
        ("负责人为 Cedar Acorn。", ["Cedar Unit", "Acorn Unit"], False),
        ("文件包括 north south.png。", ["north.png", "south.png"], False),
    ],
)
def test_chinese_connectors_separate_english_phrases(
    text: str, value: JsonValue, *, kept: bool
) -> None:
    """Terms joined by 和/与 are separate phrases; directly adjacent terms must still co-occur."""
    result = checked(text, (fact(value),))
    assert (result.dropped_sentences == ()) is kept


def test_invented_named_date_is_removed() -> None:
    """Month names cannot conceal a fabricated day or year from numeric date checks."""
    result = checked("Collection date: February 2, 2026.", (fact("2026-01-02"),))
    assert "unsupported_date" in result.dropped_sentences[0].reasons
