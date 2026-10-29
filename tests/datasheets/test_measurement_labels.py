# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Display-derived short forms retain counted objects, modifiers and numeric ownership."""

from datetime import UTC, datetime

import pytest

from datakeel.core.datasheet_models import DatasheetFact, DatasheetSection, DatasheetSentence
from datakeel.datasheets.number_labels import number_labels
from datakeel.datasheets.numeric import numeric_issues
from datakeel.datasheets.validation import validate_sections
from datakeel.datasheets.vocabulary import FIELD_LABELS


def _fact(field: str, value: int, *, identity: str = "f1") -> DatasheetFact:
    return DatasheetFact(
        id=identity,
        chapter="composition",
        source_type="version",
        source_id="v1",
        field=field,
        value=value,
        recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
    )


def test_all_existing_short_labels_remain_supported() -> None:
    """The former five-field alias table remains covered by generic measurement grammar."""
    for field, labels in (
        (
            "manifest.file_count",
            ("files", "file total", "total files", "number of files", "文件数", "文件总数"),
        ),
        (
            "assertions.count",
            (
                "assertions",
                "assertion count",
                "assertion total",
                "total assertions",
                "number of assertions",
                "断言数",
                "断言总数",
                "证据断言数",
            ),
        ),
        (
            "kg.relation_count",
            (
                "relations",
                "relation count",
                "relation total",
                "total relations",
                "number of relations",
                "关系数",
                "关系总数",
                "图谱关系数",
            ),
        ),
        ("quality.total", ("quality total", "quality rating", "质量分数", "质量得分", "质量评分")),
        (
            "compliance.total",
            ("compliance total", "compliance rating", "合规分数", "合规得分", "合规评分"),
        ),
    ):
        for label in labels:
            assert numeric_issues(f"{label}: 3.", (_fact(field, 3),)) == (), (field, label)


@pytest.mark.parametrize(
    "text",
    ["Inactive assertions: 3.", "已失效的证据断言有 3 条。"],
)
def test_inactive_short_labels_pass_full_citation_validation(text: str) -> None:
    """Both required short labels retain inactive semantics through both independent checks."""
    fact = _fact("assertions.inactive_count", 3)
    assert numeric_issues(text, (fact,)) == ()
    section = DatasheetSection(
        key="composition",
        title="Composition",
        sentences=(DatasheetSentence(text=text, fact_ids=(fact.id,)),),
    )
    assert not validate_sections((section,), (fact,), "zh").dropped_sentences


def test_short_labels_derive_from_new_display_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new registered field needs no field-specific branch or hand-maintained alias row."""
    monkeypatch.setitem(FIELD_LABELS, "custom.observation_count", ("观测数量", "Observation count"))
    monkeypatch.setitem(
        FIELD_LABELS,
        "custom.archived_observation_count",
        ("已归档观测数量", "Archived observation count"),
    )
    fact = _fact("custom.observation_count", 6).model_copy(
        update={"kind": "count", "unit": "observations"}
    )
    assert "observations" in number_labels(fact.field)
    assert numeric_issues("Observations: 6.", (fact,)) == ()
    assert numeric_issues("观测总数为 6。", (fact,)) == ()
    archived = _fact("custom.archived_observation_count", 4).model_copy(
        update={"kind": "count", "unit": "observations"}
    )
    assert numeric_issues("Archived observations: 4.", (archived,)) == ()
    assert numeric_issues("已归档的观测有 4 条。", (archived,)) == ()
    assert numeric_issues("Observations: 4.", (archived,)) == ("unsupported_number",)
    assert numeric_issues("Archived observations: 6.", (fact,)) == ("unsupported_number",)


def test_qualified_short_label_derivation_is_required() -> None:
    """The new qualified plural is derived rather than borrowing an unqualified total label."""
    fact = _fact("assertions.inactive_count", 3)
    assert numeric_issues("Inactive assertions: 3.", (fact,)) == ()
    assert numeric_issues("已失效的证据断言有 3 条。", (fact,)) == ()


def test_short_label_modifiers_cannot_be_dropped() -> None:
    """An inactive count cannot justify an assertion total, another object or a bare numeral."""
    fact = _fact("assertions.inactive_count", 3)
    for text in (
        "Assertion count: 3.",
        "Assertions: 3.",
        "证据断言数量为 3 条。",
        "断言数为 3。",
        "Inactive assertions: 3 files.",
        "已失效证据断言数量为 3 个文件。",
        "There are 3.",
        "共有 3 条。",
    ):
        assert numeric_issues(text, (fact,)) == ("unsupported_number",), text


def test_short_labels_cannot_borrow_values_across_modifiers() -> None:
    """Longer registered labels keep their own values even beside their unqualified total."""
    total = _fact("assertions.count", 13)
    inactive = _fact("assertions.inactive_count", 3, identity="f2")
    facts = (total, inactive)
    assert numeric_issues("Assertions: 13; inactive assertions: 3.", facts) == ()
    assert numeric_issues("Assertions: 3; inactive assertions: 13.", facts) == (
        "unsupported_number",
    )
    assert numeric_issues("Inactive assertions: 13.", facts) == ("unsupported_number",)
    assert numeric_issues("Inactive assertions: 13.", (total,)) == ("unsupported_number",)
    assert numeric_issues("已失效的证据断言有 13 条。", (total,)) == ("unsupported_number",)
