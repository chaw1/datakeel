# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""English grouping and filtering cues read dimension names and value aliases from contracts."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from datakeel.ask.dimensions import parse_dimensions
from datakeel.ask.models import DimensionParse
from datakeel.ask.parser import parse_question
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import DimensionDefinition, MetricCard, SemanticLayer
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database
from datakeel.storage.metric_store import install_layer

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def _parse(question: str, layer: SemanticLayer, metric_id: str) -> DimensionParse:
    """Parse dimensions with the metric's own spans excluded, exactly as the service does."""
    card = MetricCard(definition=next(item for item in layer.metrics if item.id == metric_id))
    matches = parse_question(AskRequest(question=question), layer).matches
    occupied = tuple((item.start, item.end) for item in matches if item.metric_id == metric_id)
    return parse_dimensions(question, card, layer, occupied)


@pytest.mark.parametrize(
    "question",
    [
        "retail revenue by region",
        "retail revenue per region",
        "retail revenue for each region",
        "retail revenue broken down by region",
        "retail revenue split by area",
        "region-wise retail revenue",
        "which region had the retail revenue",
        "各区域零售额",
    ],
)
def test_group_cues_before_or_after_a_dimension_name_group(
    layer: SemanticLayer, question: str
) -> None:
    """Prepositions, distributive determiners and suffixes request one row per value."""
    parsed = _parse(question, layer, "retail_revenue")
    assert parsed.group_by == ("retail_region",)
    assert parsed.slices == ()
    assert parsed.issues == ()


@pytest.mark.parametrize(
    ("question", "dimension_id", "value"),
    [
        ("retail revenue in East China", "retail_region", "华东"),
        ("retail revenue for the South China region", "retail_region", "华南"),
        ("retail revenue from Western China", "retail_region", "西部"),
        ("online retail revenue", "retail_channel", "线上"),
        ("retail revenue through distributors", "retail_channel", "经销商"),
        ("retail revenue for dishwashers", "retail_category", "洗碗机"),
        ("payment amount via e-commerce", "payment_channel", "线上"),
    ],
)
def test_value_aliases_with_filter_prepositions_become_slices(
    layer: SemanticLayer, question: str, dimension_id: str, value: str
) -> None:
    """English value aliases resolve to the canonical stored value of the metric's dimension."""
    metric_id = "payment_amount" if question.startswith("payment") else "retail_revenue"
    parsed = _parse(question, layer, metric_id)
    assert [(item.dimension_id, item.value) for item in parsed.slices] == [(dimension_id, value)]
    assert parsed.issues == ()


_UNSUPPORTED_ROLES = [
    "retail revenue excluding East China",
    "retail revenue except online",
    "retail revenue outside East China",
    "除了华东以外的零售额",
    "retail revenue for each East China",
    "retail revenue in East China and South China",
    "refund amount per channel",
    "retail revenue region",
]


def _assert_reported(layer: SemanticLayer, question: str) -> None:
    """Keep an unsupported role as an issue and never turn it into a slice."""
    metric_id = "refund_amount" if question.startswith("refund") else "retail_revenue"
    parsed = _parse(question, layer, metric_id)
    assert parsed.issues, question
    assert parsed.slices == (), question


@pytest.mark.parametrize("question", _UNSUPPORTED_ROLES)
def test_unsupported_dimension_roles_are_reported(layer: SemanticLayer, question: str) -> None:
    """Exclusions, per-value grouping, conflicting values and foreign dimensions never vanish."""
    _assert_reported(layer, question)


def test_no_unsupported_dimension_role_becomes_a_slice(layer: SemanticLayer) -> None:
    """One sweep over every unsupported role for guard mutations."""
    for question in _UNSUPPORTED_ROLES:
        _assert_reported(layer, question)


def test_value_aliases_are_read_from_the_contract_not_code(layer: SemanticLayer) -> None:
    """Renaming an alias in data changes recognition; removing it leaves the phrase unconsumed."""
    renamed = _with_region_aliases(layer, {"华东": ["Yangtze Delta"]})
    parsed = _parse("retail revenue in Yangtze Delta", renamed, "retail_revenue")
    assert [(item.dimension_id, item.value) for item in parsed.slices] == [
        ("retail_region", "华东")
    ]
    assert _parse("retail revenue in Yangtze Delta", layer, "retail_revenue").slices == ()
    stripped = _with_region_aliases(layer, {})
    assert _parse("retail revenue in East China", stripped, "retail_revenue").slices == ()


def test_value_synonyms_are_optional_and_validated() -> None:
    """Older contracts load unchanged; aliases must point at declared values and contain text."""
    legacy = DimensionDefinition.model_validate(
        {"id": "zone", "name": "区域", "column": "zone", "values": ["华东"]}
    )
    assert legacy.value_synonyms == {}
    assert "value_synonyms" not in legacy.model_dump()
    with pytest.raises(ValidationError):
        DimensionDefinition.model_validate(
            {
                "id": "zone",
                "name": "区域",
                "column": "zone",
                "values": ["华东"],
                "value_synonyms": {"华西": ["West"]},
            }
        )
    with pytest.raises(ValidationError):
        DimensionDefinition.model_validate(
            {
                "id": "zone",
                "name": "区域",
                "column": "zone",
                "values": ["华东"],
                "value_synonyms": {"华东": [" "]},
            }
        )


def test_shipped_contract_gives_every_dimension_and_value_an_english_alias(
    layer: SemanticLayer,
) -> None:
    """The example semantic layer is usable in English without code-level translation tables."""
    for dimension in layer.dimensions:
        assert dimension.english_name, dimension.id
        assert any(name.isascii() for name in dimension.synonyms), dimension.id
        for value in dimension.values:
            assert any(alias.isascii() for alias in dimension.value_synonyms[value]), value


@pytest.mark.parametrize(
    ("english", "chinese"),
    [
        ("retail revenue by region last quarter", "上个季度各区域零售额"),
        ("retail revenue in East China last quarter", "上个季度华东区零售额"),
        ("online retail revenue in Q2 2026", "2026年第二季度线上零售额"),
        ("sales amount per channel in March 2026", "2026年3月按渠道销售额"),
    ],
)
def test_english_filters_and_groups_equal_the_chinese_answers(
    db: Database, enterprise_sample: EnterpriseSample, english: str, chinese: str
) -> None:
    """English slices and groupings produce exactly the Chinese rows."""
    assert enterprise_sample.sources
    expected = ask_data(db, AskRequest(question=chinese, reference_instant=REFERENCE))
    answer = ask_data(db, AskRequest(question=english, reference_instant=REFERENCE))
    assert expected.status == answer.status == "answered", (english, answer.message)
    assert answer.result == expected.result
    assert answer.interpretation == expected.interpretation


def test_custom_contract_alias_reaches_the_answer(
    db: Database, enterprise_sample: EnterpriseSample, layer: SemanticLayer
) -> None:
    """An alias added only in the installed contract filters the executed query."""
    assert enterprise_sample.sources
    install_layer(db, _with_region_aliases(layer, {"华东": ["Yangtze Delta"]}))
    answer = ask_data(
        db, AskRequest(question="retail revenue in Yangtze Delta", reference_instant=REFERENCE)
    )
    expected = ask_data(db, AskRequest(question="华东区零售额", reference_instant=REFERENCE))
    assert answer.status == expected.status == "answered"
    assert answer.result == expected.result


def _with_region_aliases(layer: SemanticLayer, aliases: dict[str, list[str]]) -> SemanticLayer:
    dimensions = [
        item.model_copy(update={"value_synonyms": aliases}) if item.id == "retail_region" else item
        for item in layer.dimensions
    ]
    return layer.model_copy(update={"dimensions": dimensions})
