# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Numbers are checked with their units: percentages need ratios, units must agree."""

from datetime import UTC, datetime

import pytest
from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact, DatasheetSection, DatasheetSentence
from datakeel.core.datasheet_types import DatasheetValueKind, fact_type
from datakeel.datasheets.matching import fact_readings, numeric_issues
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
        ("custom.image_share: 98.3.", "custom.image_share", 98.3, PERCENT),
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
    assert {unit for _value, unit in fact_readings(table)} == {"count:files"}
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


@pytest.mark.parametrize(
    ("text", "field", "value"),
    [
        ("The dataset contains 54 files.", "kg.relation_count", 54),
        ("数据集包含54个文件。", "kg.relation_count", 54),
        ("The graph contains 50 relations.", "manifest.file_count", 50),
        ("图谱包含50条关系。", "manifest.file_count", 50),
        ("Evidence assertion count: 54 assertions.", "kg.relation_count", 54),
        ("数据集包含54张图片。", "kg.relation_count", 54),
    ],
)
def test_counting_a_different_object_is_dropped(text: str, field: str, value: int) -> None:
    """Equal counts cannot exchange files, relations, assertions or images across objects."""
    assert "unsupported_number" in _reasons(text, _fact(field, value))


@pytest.mark.parametrize(
    ("text", "field", "value", "declared"),
    [
        ("The dataset contains 50 files.", "manifest.file_count", 50, {}),
        ("数据集包含50个文件。", "manifest.file_count", 50, {}),
        ("The graph contains 54 relations.", "kg.relation_count", 54, {}),
        ("图谱包含54条关系。", "kg.relation_count", 54, {}),
        ("Evidence assertion count: 12 assertions.", "assertions.count", 12, {}),
        ("数据集包含200张图片。", "custom.images", 200, {"kind": "count", "unit": "images"}),
        ("文件数量=50个。", "manifest.file_count", 50, {}),
        ("图谱关系数量=54条。", "kg.relation_count", 54, {}),
        ("The dataset contains 50 image files.", "manifest.file_count", 50, {}),
    ],
)
def test_counting_the_same_object_and_labelled_classifiers_are_kept(
    text: str, field: str, value: int, declared: dict[str, object]
) -> None:
    """A precise object noun or the matching field label retains the intended count."""
    assert _reasons(text, _fact(field, value, **declared)) == ()


@pytest.mark.parametrize(
    ("text", "field", "value", "declared"),
    [
        ("There are 54.", "kg.relation_count", 54, {}),
        ("The dataset contains 50.", "manifest.file_count", 50, {}),
        ("数据集共有54。", "kg.relation_count", 54, {}),
        ("数据集包含50。", "manifest.file_count", 50, {}),
        ("The quality score is 54.", "kg.relation_count", 54, {}),
        ("Total bytes: 54.", "kg.relation_count", 54, {}),
        ("Image percentage: 0.983.", "custom.image_share", 98.3, PERCENT),
        ("There are 54.", "custom.cost", 54, {"kind": "amount", "unit": None}),
        ("数据集共有54个。", "custom.total", 54, {"kind": "count", "unit": None}),
    ],
)
def test_bare_numbers_cannot_borrow_an_unlabelled_typed_value(
    text: str, field: str, value: float, declared: dict[str, object]
) -> None:
    """A typed value supports a bare numeral only under that fact's own field label."""
    assert "unsupported_number" in _reasons(text, _fact(field, value, **declared))


@pytest.mark.parametrize(
    ("text", "field", "value", "declared"),
    [
        ("File count=50.", "manifest.file_count", 50, {}),
        ("文件数量为50。", "manifest.file_count", 50, {}),
        ("Relation count: 54.", "kg.relation_count", 54, {}),
        ("图谱关系数量=54。", "kg.relation_count", 54, {}),
        ("Quality score=87.5.", "quality.total", 87.5, {}),
        ("质量总分为87.5。", "quality.total", 87.5, {}),
        ("There are 54.", "custom.value", 54, {}),
        ("数据集有54。", "custom.note", "54", {}),
        ("There are 54.", "custom.record", {"value": 54}, {}),
    ],
)
def test_labelled_bare_numbers_and_untyped_values_are_kept(
    text: str, field: str, value: JsonValue, declared: dict[str, object]
) -> None:
    """Exact label/value pairs survive, while number, text and record facts stay untyped."""
    assert _reasons(text, _fact(field, value, **declared)) == ()


def test_count_object_guard_is_required() -> None:
    """Collapsing relations into file counts exposes the original cross-object acceptance."""
    assert _reasons("The dataset contains 54 files.", _fact("kg.relation_count", 54)) == (
        "unsupported_number",
    )


def test_bare_number_guard_is_required() -> None:
    """Value equality alone cannot justify an unlabelled cardinal from a measured fact."""
    assert _reasons("There are 54.", _fact("kg.relation_count", 54)) == ("unsupported_number",)


def test_nearby_labels_do_not_lend_their_value_to_another_label() -> None:
    """One correct relation count cannot launder the wrong file count in the same sentence."""
    files = _fact("manifest.file_count", 50)
    relations = _fact("kg.relation_count", 54).model_copy(update={"id": "f2"})
    assert "unsupported_number" in _cited_reasons(
        "File count=54 and relation count=54.", files, relations
    )
    assert _cited_reasons("File count=50 and relation count=54.", files, relations) == ()


def test_count_noun_phrases_retain_their_head_object() -> None:
    """Text observations are observations, and image files remain files in both languages."""
    observation = _fact("metadata.description", "200 generated text observations")
    assert _reasons("The dataset contains 200 observations.", observation) == ()
    assert _reasons("数据集包含200条文本观测。", observation) == ()


@pytest.mark.parametrize(
    ("text", "field", "value", "drop"),
    [
        ("The archive holds 12 evidence assertions.", "assertions.count", 12, False),
        ("该数据集包含 12 个 files。", "manifest.file_count", 12, False),
        (
            "包含 7 个 audio 文件和 5 个 text 文件。",
            "manifest.modalities",
            {"audio": 7, "text": 5},
            False,
        ),
        (
            "70 assertions are accepted and 30 are rejected.",
            "assertions.status_counts",
            {"accepted": 70, "rejected": 30},
            False,
        ),
        ("图谱关系数为 12 条。", "kg.relation_count", 12, False),
        ("Assertion count = 12.", "assertions.count", 12, False),
        ("The archive holds 12 files.", "assertions.count", 12, True),
        ("该数据集包含 12 条断言。", "manifest.file_count", 12, True),
        ("图谱实体数为 12 个。", "kg.relation_count", 12, True),
        ("The release has 12 reviewers.", "assertions.count", 12, True),
        ("Version 12 is current.", "assertions.count", 12, True),
        ("包含 7 个 image 文件。", "manifest.modalities", {"audio": 7, "text": 5}, True),
    ],
)
def test_fix1_required_numeric_cases(
    text: str, field: str, value: JsonValue, *, drop: bool
) -> None:
    """All twelve review examples retain their original wording and direct numeric verdict."""
    assert bool(numeric_issues(text, (_fact(field, value),))) is drop


@pytest.mark.parametrize(
    ("text", "field", "value"),
    [
        ("The release contains 23 retained evidence assertions.", "assertions.count", 23),
        ("该归档包含 23 条 evidence assertions。", "assertions.count", 23),
        ("Assertion total: 23.", "assertions.count", 23),
        ("共标注8158条证据。", "assertions.count", 8158),
        ("质量评分为满分100.0。", "quality.total", 100.0),
        ("The data quality rating is a perfect 100.", "quality.total", 100.0),
        ("The archive stores 41 newly imported files.", "manifest.file_count", 41),
        ("The archive has 41 files stored locally.", "manifest.file_count", 41),
        ("23 evidence assertions remain available.", "assertions.count", 23),
        ("文件总数为 41 个。", "manifest.file_count", 41),
        ("该批次含 41 个 labelled image files。", "manifest.file_count", 41),
        (
            "There are 9 audio files and 4 text files.",
            "manifest.modalities",
            {"audio": 9, "text": 4},
        ),
        ("9 files are audio and 4 are text.", "manifest.modalities", {"audio": 9, "text": 4}),
        ("9 table files and 4 unknown files.", "manifest.modalities", {"table": 9, "unknown": 4}),
        ("9 files are audio while 4 are text.", "manifest.modalities", {"audio": 9, "text": 4}),
        ("9 audio files plus 4 text files.", "manifest.modalities", {"audio": 9, "text": 4}),
        (
            "61 assertions were accepted and 14 were rejected.",
            "assertions.status_counts",
            {"accepted": 61, "rejected": 14},
        ),
        (
            "Accepted: 61; rejected: 14.",
            "assertions.status_counts",
            {"accepted": 61, "rejected": 14},
        ),
        (
            "Accepted assertions: 61, rejected assertions: 14.",
            "assertions.status_counts",
            {"accepted": 61, "rejected": 14},
        ),
    ],
)
def test_numeric_paraphrases_keep_their_measurement(
    text: str, field: str, value: JsonValue
) -> None:
    """Modifiers, bilingual classifiers, short labels and omitted repeated nouns are supported."""
    assert numeric_issues(text, (_fact(field, value),)) == ()


@pytest.mark.parametrize(
    ("text", "field", "value"),
    [
        ("Evidence assertion count: 23 reviewers.", "assertions.count", 23),
        ("File count: 41 reviewers.", "manifest.file_count", 41),
        ("File count: 41 of the reviewers.", "manifest.file_count", 41),
        ("文件总数为 41 条关系。", "manifest.file_count", 41),
        ("共标注8158条证据。", "kg.relation_count", 8158),
        (
            "There are 9 text files and 4 audio files.",
            "manifest.modalities",
            {"audio": 9, "text": 4},
        ),
        ("Audio: 4; text: 9.", "manifest.modalities", {"audio": 9, "text": 4}),
        (
            "14 assertions were accepted and 61 were rejected.",
            "assertions.status_counts",
            {"accepted": 61, "rejected": 14},
        ),
        (
            "61 assertions were rejected and 14 were accepted.",
            "assertions.status_counts",
            {"accepted": 61, "rejected": 14},
        ),
        (
            "Accepted: 14; rejected: 61.",
            "assertions.status_counts",
            {"accepted": 61, "rejected": 14},
        ),
        ("Assertion count=23.", "assertions.inactive_count", 23),
    ],
)
def test_numeric_paraphrases_cannot_exchange_objects_or_record_keys(
    text: str, field: str, value: JsonValue
) -> None:
    """A matching label never erases an explicit object or exchanges two count-table values."""
    assert numeric_issues(text, (_fact(field, value),)) == ("unsupported_number",)


def test_short_labels_bind_only_their_own_number() -> None:
    """Two concise labels cannot exchange cited counts even when both facts are available."""
    facts = (_fact("manifest.file_count", 41), _fact("kg.relation_count", 23))
    assert numeric_issues("Files: 41; relations: 23.", facts) == ()
    assert numeric_issues("Files: 23; relations: 23.", facts) == ("unsupported_number",)


def test_count_modifier_support_is_required() -> None:
    """The head noun remains recognizable after arbitrary count modifiers."""
    assert (
        numeric_issues(
            "The archive holds 23 retained evidence assertions.", (_fact("assertions.count", 23),)
        )
        == ()
    )
    assert (
        numeric_issues("23 evidence assertions remain available.", (_fact("assertions.count", 23),))
        == ()
    )

    assert (
        numeric_issues(
            "File count: 41 files supporting reviewers.", (_fact("manifest.file_count", 41),)
        )
        == ()
    )


def test_short_measurement_label_support_is_required() -> None:
    """A common short label retains the same counted object as the full display label."""
    assert numeric_issues("图谱关系数为 23 条。", (_fact("kg.relation_count", 23),)) == ()


def test_record_key_binding_is_required() -> None:
    """An unmentioned modality cannot borrow another key's equal typed count."""
    assert numeric_issues(
        "There are 9 image files.", (_fact("manifest.modalities", {"audio": 9, "text": 4}),)
    ) == ("unsupported_number",)


def test_parallel_predicate_binding_is_required() -> None:
    """An omitted noun retains its own following status, not the previous status."""
    assert (
        numeric_issues(
            "61 assertions were accepted and 14 were rejected.",
            (_fact("assertions.status_counts", {"accepted": 61, "rejected": 14}),),
        )
        == ()
    )


def test_explicit_unknown_noun_cannot_borrow_a_label() -> None:
    """A count label cannot turn an unfamiliar noun into the recorded object."""
    assert numeric_issues("File count: 41 contributors.", (_fact("manifest.file_count", 41),)) == (
        "unsupported_number",
    )
    assert numeric_issues(
        "File count: 41 of the reviewers.", (_fact("manifest.file_count", 41),)
    ) == ("unsupported_number",)

    assert numeric_issues(
        "Assertion count: 23 files containing assertions.", (_fact("assertions.count", 23),)
    ) == ("unsupported_number",)


def test_record_keys_keep_their_parent_measurement() -> None:
    """A predicate named files still counts assertions, and same keys retain their table."""
    predicates = _fact("assertions.predicate_counts", {"files": 9, "relations": 4})
    assert numeric_issues("9 files.", (predicates,)) == ("unsupported_number",)
    assert numeric_issues("Files: 9 assertions.", (predicates,)) == ()
    facts = (
        _fact("assertions.status_counts", {"accepted": 61, "rejected": 14}),
        _fact("assertions.verification_counts", {"accepted": 7, "rejected": 3}),
    )
    assert numeric_issues("Evidence verification counts: accepted=61.", facts) == (
        "unsupported_number",
    )
    assert numeric_issues("Evidence verification counts: accepted=7.", facts) == ()


def test_nearest_modality_cannot_be_overridden_by_a_later_key() -> None:
    """An explicit image modifier cannot borrow an audio count elsewhere in the clause."""
    assert numeric_issues(
        "9 image files of audio.", (_fact("manifest.modalities", {"audio": 9, "text": 4}),)
    ) == ("unsupported_number",)


def test_bare_percent_restatements_require_the_actual_scale_and_measurement() -> None:
    """The original disputed examples cannot silently rescale percentages into bare scores."""
    assert numeric_issues(
        "Image percentage: 0.983.", (_fact("custom.image_share", 98.3, **PERCENT),)
    ) == ("unsupported_number",)
    assert numeric_issues("The quality score is 0.983.", (_fact("custom.value", "98.3%"),)) == (
        "unsupported_number",
    )
    assert _reasons("The quality score is 0.983.", _fact("quality.total", 0.983)) == ()


def test_chinese_parallel_counts_keep_each_key_and_object() -> None:
    """Common conjunctions separate modality counts without exchanging their evidence."""
    facts = (_fact("manifest.modalities", {"audio": 8, "text": 6}),)
    for conjunction in ("和", "与", "以及", "及", "、"):
        assert numeric_issues(f"包含8个 audio 文件{conjunction}6个 text 文件。", facts) == ()
        assert numeric_issues(f"包含6个 audio 文件{conjunction}8个 text 文件。", facts) == (
            "unsupported_number",
        )


def test_record_keys_can_follow_numbers_with_the_object_omitted() -> None:
    """A trailing record key names its value even when its word is not a count noun."""
    modalities = (_fact("manifest.modalities", {"text": 8, "audio": 6}),)
    assert numeric_issues("8 text files and 6 audio.", modalities) == ()
    assert numeric_issues("包含8个 text 文件和6个 audio。", modalities) == ()
    assert numeric_issues("8 text files and 8 audio.", modalities) == ("unsupported_number",)
    verification = (_fact("assertions.verification_counts", {"verified": 17, "unverifiable": 9}),)
    assert numeric_issues("17 assertions verified and 9 unverifiable.", verification) == ()


def test_record_key_labels_cannot_erase_explicit_foreign_objects() -> None:
    """A matching key before a number cannot cover an unrelated object after that number."""
    facts = (_fact("manifest.modalities", {"text": 8, "audio": 6}),)
    for noun in ("contributors", "relations"):
        assert numeric_issues(f"8 text files and audio: 6 {noun}.", facts) == (
            "unsupported_number",
        )
