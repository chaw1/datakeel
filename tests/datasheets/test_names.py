# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Names cannot be synthesized from grammar words or separately supported numerals."""

from datetime import UTC, datetime

import pytest
from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact, DatasheetSection, DatasheetSentence
from datakeel.datasheets.validation import validate_sections


def _check(text: str, value: JsonValue) -> bool:
    fact = DatasheetFact(
        id="f1",
        chapter="composition",
        source_type="manifest",
        source_id="fixture",
        field="manifest.file_count",
        value=value,
        recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
    )
    result = validate_sections(
        (
            DatasheetSection(
                key="composition",
                title="Composition",
                sentences=(DatasheetSentence(text=text, fact_ids=("f1",)),),
            ),
        ),
        (fact,),
    )
    return bool(result.sections[1].sentences) and not result.dropped_sentences


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("负责人为张三。", 3),
        ("张三有3个文件。", 3),
        ("一二三组织有123个文件。", 123),
        ("负责人为张一。", 1),
        ("负责人为“张三”。", 3),
        ("张三负责维护数据集。", 3),
        ("张三创建了数据集。", 3),
        ("数据集由张三维护。", 3),
        ("一二三组织维护本数据集。", 123),
        ("负责人为「一二三组织」。", 123),
        ('The owner is "3".', 3),
        ('The owner is "Open Data".', 3),
        ("Owned by Data Open.", 3),
        ("Owned by data open.", 3),
        ("Open Data is the owner.", 3),
        ("The owner is open data.", 3),
        ("Owner: open data.", 3),
        ("The dataset is named open data.", 3),
        ("The dataset is called open data.", 3),
        ("The owner is Cedar Unit and open data.", ["Cedar Unit", 3]),
        ('The dataset is called "123".', 123),
        ("Data Open contains 3 files.", 3),
        ("Open Data contains 3 files.", 3),
        ("The owner is Data.", "dataset"),
        ("Owner='ONE'.", 1),
        ("Owner Three.", 3),
        ("Owner='1,234'.", 1234),
    ],
)
def test_explicit_unrecorded_identity_is_rejected(text: str, value: JsonValue) -> None:
    """An existing numeric fact or common word never establishes a newly named owner."""
    assert not _check(text, value)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Three images.", 3),
        ("The dataset contains \u20181,234\u2019 files.", 1234),
        ("The dataset contains “one” file.", 1),
        ("The dataset contains “三” images.", 3),
        ("Owner='ONE'.", "ONE"),
        ("Owner Three.", "Three"),
        ("ONE file.", 1),
        ("三张图片。", 3),
        ("负责人为张三。", "张三"),
        ("负责人为“张三”。", "张三"),
        ("张三负责维护数据集。", "张三"),
        ("数据集由张三维护。", "张三"),
        ("一二三组织维护本数据集。", "一二三组织"),
        ("The owner is Open Data.", "Open Data"),
        ('The owner is "Open Data".', "Open Data"),
        ('The dataset is called "123".', "123"),
        ("Owned by Cedar Unit.", "Cedar Unit"),
        ("The owner is Cedar Unit and Acorn Unit.", ["Cedar Unit", "Acorn Unit"]),
        (
            "The dataset contains three image files. It is maintained by Cedar Unit.",
            [3, "image", "Cedar Unit"],
        ),
        ("该数据集包含三张图片。数据集由星河团队维护。", [3, "星河团队"]),
    ],
)
def test_recorded_identities_and_natural_paragraphs_are_retained(
    text: str, value: JsonValue
) -> None:
    """The stronger name boundary preserves cited quantities and real bilingual owners."""
    assert _check(text, value)
