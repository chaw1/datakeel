# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Numbers are checked with their units: percentages need ratios, units must agree."""

from datetime import UTC, datetime

import pytest
from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact, DatasheetSection, DatasheetSentence
from datakeel.core.datasheet_types import DatasheetValueKind, fact_type
from datakeel.datasheets.matching import fact_readings
from datakeel.datasheets.validation import validate_sections


def _fact(field: str, value: JsonValue, **declared: object) -> DatasheetFact:
    return DatasheetFact.model_validate(
        {
            "id": "f1",
            "chapter": "composition",
            "source_type": "version",
            "source_id": "v1",
            "field": field,
            "value": value,
            "recorded_at": datetime(2026, 10, 27, tzinfo=UTC),
            **declared,
        }
    )


def _reasons(text: str, fact: DatasheetFact) -> tuple[str, ...]:
    section = DatasheetSection(
        key="composition",
        title="Composition",
        sentences=(DatasheetSentence(text=text, fact_ids=(fact.id,)),),
    )
    result = validate_sections((section,), (fact,), "zh")
    return tuple(reason for item in result.dropped_sentences for reason in item.reasons)


RATIO = {"kind": "ratio", "unit": "ratio"}
PERCENT = {"kind": "percent", "unit": "percent"}
USD = {"kind": "amount", "unit": "USD"}


@pytest.mark.parametrize(
    ("text", "field", "value", "declared"),
    [
        ("Image ratio: 98.3%.", "custom.image_ratio", 0.983, RATIO),
        ("Image ratio: 98.3 percent.", "custom.image_ratio", 0.983, RATIO),
        ("Image ratio: 0.983 (ratio).", "custom.image_ratio", 0.983, RATIO),
        ("Image percentage: 98.3%.", "custom.image_share", 98.3, PERCENT),
        ("Image percentage: 0.983.", "custom.image_share", 98.3, PERCENT),
        ("Image ratio: fifty percent.", "custom.image_ratio", 0.5, RATIO),
        ("Labelled images: 98.3%.", "metadata.description", "98.3% labelled images", {}),
        ("Total bytes: 4,815,739 bytes.", "manifest.total_bytes", 4815739, {}),
        ("总字节数为4815739字节。", "manifest.total_bytes", 4815739, {}),
        ("数据集共有398个文件。", "manifest.file_count", 398, {}),
        ("The dataset contains 398 files.", "manifest.file_count", 398, {}),
        ("质量总分为100.0分。", "quality.total", 100.0, {}),
        ("Quality score: 100 points.", "quality.total", 100.0, {}),
        ("The cost is $1.72.", "custom.cost", 1.72, USD),
        ("The cost is 1.72 USD.", "custom.cost", 1.72, USD),
        ("版本创建于2026年10月。", "version.created_at", "2026-10-27T15:55:01+00:00", {}),
        ("数据集包含200张图片。", "metadata.description", "200 generated images", {}),
    ],
)
def test_numbers_with_matching_units_are_kept(
    text: str, field: str, value: JsonValue, declared: dict[str, object]
) -> None:
    """Ratios may be written as percentages and every stated unit matches the fact's unit."""
    assert _reasons(text, _fact(field, value, **declared)) == ()


@pytest.mark.parametrize(
    ("text", "field", "value", "declared"),
    [
        ("50% of the files are images.", "manifest.file_count", 50, {}),
        ("文件数量为50%。", "manifest.file_count", 50, {}),
        ("合规总分为99.92%。", "compliance.total", 99.92, {}),
        ("Custom value: 50%.", "custom.value", 50, {}),
        (
            "合规问题\uff1anaming compliance is 99.75%。",
            "compliance.issues",
            ["naming compliance is 99.75/100"],
            {},
        ),
        ("Image ratio: fifty percent.", "custom.image_ratio", 50, {}),
        ("Image ratio: 0.983%.", "custom.image_ratio", 0.983, RATIO),
        ("The dataset contains 4,815,739 files.", "manifest.total_bytes", 4815739, {}),
        ("数据集共有4815739个文件。", "manifest.total_bytes", 4815739, {}),
        ("总字节数为398字节。", "manifest.file_count", 398, {}),
        ("质量总分为398分。", "manifest.file_count", 398, {}),
        ("处理耗时398秒。", "manifest.file_count", 398, {}),
        ("数据集共有100个文件。", "quality.total", 100.0, {}),
        ("The cost is 1.72元.", "custom.cost", 1.72, USD),
        ("The cost is ¥1.72.", "custom.cost", 1.72, USD),
        ("数据集共有2026个文件。", "version.created_at", "2026-10-27T15:55:01+00:00", {}),
    ],
)
def test_numbers_under_another_unit_are_dropped(
    text: str, field: str, value: JsonValue, declared: dict[str, object]
) -> None:
    """A percentage needs a ratio and a stated unit needs a fact measured in that unit."""
    assert "unsupported_number" in _reasons(text, _fact(field, value, **declared))


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("manifest.file_count", 3, ("count", "files")),
        ("manifest.filenames.2", ["a.txt"], ("name", None)),
        ("custom.flag", True, ("status", None)),
        ("custom.ratio", 0.5, ("number", None)),
        ("custom.table", {"a": 1}, ("record", None)),
        ("custom.note", "free text", ("text", None)),
    ],
)
def test_fact_kind_comes_from_the_field_or_the_value_shape(
    field: str, value: JsonValue, expected: tuple[DatasheetValueKind, str | None]
) -> None:
    """Declared fields carry their meaning; unknown fields only describe their JSON shape."""
    assert fact_type(field, value) == expected
    fact = _fact(field, value)
    assert (fact.kind, fact.unit) == expected


def test_explicit_kind_is_preserved_and_measured_leaves_share_it() -> None:
    """Callers may declare a kind, and every numeric leaf of a count table is a count."""
    table = _fact("manifest.modalities", {"image": 200, "text": 198})
    assert {unit for _value, unit in fact_readings(table)} == {"count"}
    ratio = _fact("custom.share", 0.5, kind="ratio", unit=None)
    assert ratio.kind == "ratio"
    assert ratio.model_copy() == DatasheetFact.model_validate(ratio.model_dump(mode="json"))


def _cited_reasons(text: str, *facts: DatasheetFact) -> tuple[str, ...]:
    section = DatasheetSection(
        key="composition",
        title="Composition",
        sentences=(DatasheetSentence(text=text, fact_ids=tuple(fact.id for fact in facts)),),
    )
    result = validate_sections((section,), facts, "zh")
    return tuple(reason for item in result.dropped_sentences for reason in item.reasons)


@pytest.mark.parametrize(
    ("text", "reasons"),
    [
        ("质量总分为87.5分\uff0c版本创建时间为2026-10-27T21:26:46.777104+00:00。", ()),
        ("质量总分为87.5分\uff0c版本创建于2026-10-27 21:26。", ()),
        ("质量总分为87.5分\uff0c版本创建于10月27日。", ()),
        ("质量总分为27\uff0c版本创建于2026-10-27。", ("unsupported_number",)),
        ("质量总分为21\uff0c版本创建于2026-10-27。", ("unsupported_number",)),
        ("质量总分为46\uff0c版本创建于2026-10-27。", ("unsupported_number",)),
        ("质量总分为87.5分\uff0c版本创建于10月21日。", ("unsupported_number",)),
        ("质量总分为87.5分\uff0c版本创建于2026-10-27 21:46。", ("unsupported_date",)),
        ("质量总分为87.5分\uff0c版本创建于2026-10-27 22:26。", ("unsupported_date",)),
        (
            "质量总分为87.5分\uff0c版本创建于2026-10-27T21:26:46.999999+00:00。",
            ("unsupported_date",),
        ),
    ],
)
def test_date_and_clock_parts_are_never_loose_numbers(text: str, reasons: tuple[str, ...]) -> None:
    """A cited timestamp supports its whole date and clock, not a bare day, hour or second."""
    score = _fact("quality.total", 87.5)
    created = _fact("version.created_at", "2026-10-27T21:26:46.777104+00:00").model_copy(
        update={"id": "f2"}
    )
    assert _cited_reasons(text, score, created) == reasons
