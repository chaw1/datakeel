# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline templates read as prose while every sentence stays checkable against its fact."""

from datetime import UTC, datetime

import pytest
from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact, DatasheetLanguage
from datakeel.datasheets import templates
from datakeel.datasheets.templates import build_template


def _fact(field: str, value: JsonValue) -> DatasheetFact:
    return DatasheetFact(
        id="fact-structured",
        chapter="composition",
        source_type="manifest",
        source_id="version-a",
        field=field,
        value=value,
        recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
    )


def _text(field: str, value: JsonValue, language: DatasheetLanguage) -> str:
    result = build_template((_fact(field, value),), language)
    assert result.dropped_sentences == ()
    (sentence,) = result.sections[1].sentences
    assert sentence.fact_ids == ("fact-structured",)
    return sentence.text


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (
            "manifest.filenames.1",
            ["note-000.txt", "note-001.txt"],
            "File names: note-000.txt, note-001.txt",
        ),
        (
            "quality.dimensions",
            {
                "completeness": {"score": 100.0, "weight": 33.3, "details": {"passed": 3}},
                "annotation": {"score": 0.0, "included": False},
            },
            "Quality dimensions: completeness: 100.0; annotation: 0.0",
        ),
        (
            "quality.issues",
            [
                {
                    "dimension": "annotation",
                    "severity": "info",
                    "message": "No annotation evidence; remaining weights are normalized.",
                },
                {"dimension": "consistency", "message": "consistency: 81.82/100"},
                {"severity": "warning", "message": "Review pending"},
            ],
            (
                "Quality issues: annotation: No annotation evidence; remaining weights are "
                "normalized; consistency: 81.82/100; Review pending"
            ),
        ),
        (
            "kg.entities",
            [
                {"name": "Maya Chen", "type": "person"},
                {"name": "Ingestion Team", "type": "organization"},
                {"name": "Data Engineering"},
            ],
            "Graph entities: person: Maya Chen; organization: Ingestion Team; Data Engineering",
        ),
        ("custom.records", [{"a": 1, "b": "x"}, {"a": 2}], "custom.records: a: 1, b: x; a: 2"),
        (
            "custom.nested",
            {"group": {"a": 1}, "names": ["a1", "b2"]},
            ("custom.nested: group (a: 1); names: a1, b2"),
        ),
    ],
)
def test_structured_values_read_without_json_punctuation(
    field: str, value: JsonValue, expected: str
) -> None:
    """Lists, scored dimensions, issues and entities become labelled readable text."""
    assert _text(field, value, "en") == expected


def test_chinese_templates_use_chinese_list_punctuation() -> None:
    """Chinese sheets separate items with enumeration commas and records with semicolons."""
    value: JsonValue = {"names": ["a1", "b2"], "count": 2}
    assert _text("custom.names", value, "zh") == (
        "custom.names\uff1anames\uff1aa1\u3001b2\uff1bcount\uff1a2"
    )


@pytest.mark.parametrize(
    "value",
    [
        [],
        [1, {"a": 1}],
        [{"a": {"b": 1}}],
        {"group": {"a": {"b": 1}}},
        {"group": [1, {"a": 1}]},
    ],
)
def test_values_without_a_readable_shape_stay_literal_json(value: JsonValue) -> None:
    """Deeply nested or mixed values are never summarized away; they are shown verbatim."""
    text = _text("custom.field", value, "en")
    assert text.startswith("custom.field: ")
    assert text.removeprefix("custom.field: ")[0] in "[{"


def test_readable_text_that_fails_validation_falls_back_to_the_literal_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The readable form is only kept when the independent citation check accepts it alone."""

    def fabricated(fact: DatasheetFact, language: DatasheetLanguage) -> str:
        assert fact.field == "custom.records"
        assert language == "en"
        return "Fabricated Labs owns it."

    monkeypatch.setattr(templates, "fact_text", fabricated)
    assert _text("custom.records", [{"a": 1}], "en") == 'custom.records: [{"a": 1}]'
