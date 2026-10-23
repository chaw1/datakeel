# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact, synonym, glossary, and conservative-prefix matching retain text evidence."""

from datetime import UTC, datetime

from datakeel.ask.matching import metric_matches, occurrences
from datakeel.ask.parser import parse_question
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import SemanticLayer, TermDefinition, TermTarget

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def test_parse_question_metric_region_time_have_valid_nfc_anchors(layer: SemanticLayer) -> None:
    """The canonical example contains registered metric and calendar anchors."""
    request = AskRequest(question="上个季度华东区零售额是多少", reference_instant=REFERENCE)
    parsed = parse_question(request, layer)
    assert {match.metric_id for match in parsed.matches} >= {"retail_revenue"}
    assert any(match.source == "time:last_quarter" for match in parsed.matches)
    assert all(request.question[match.start : match.end] == match.text for match in parsed.matches)
    assert parsed.time_range is not None
    assert parsed.time_range.start.isoformat() == "2026-07-01"
    assert parsed.time_range.end.isoformat() == "2026-10-01"


def test_metric_matching_glossary_column_maps_only_registered_measures(
    layer: SemanticLayer,
) -> None:
    """A term pointing to a measured column can locate its registered metric."""
    matches = metric_matches("消费者实付是多少", layer)
    assert any(
        match.metric_id == "retail_revenue" and match.term_id == "term/终端实付金额"
        for match in matches
    )
    assert metric_matches("工单日期", layer) == ()


def test_metric_matching_conservative_prefix_ignores_unrelated_words(layer: SemanticLayer) -> None:
    """Incomplete names can match at phrase boundaries without guessing customer satisfaction."""
    assert any(item.match_kind == "prefix" for item in metric_matches("零售是多少", layer))
    assert metric_matches("客户满意度如何", layer) == ()


def test_metric_matching_empty_synonyms_and_unknown_targets_never_match_all(
    layer: SemanticLayer,
) -> None:
    """Blank vocabulary entries and stale term references cannot create metric candidates."""
    metric = layer.metrics[0].model_copy(update={"synonyms": ["", "   "]})
    modified = layer.model_copy(
        update={
            "metrics": [metric],
            "terms": [
                TermDefinition(
                    term="幽灵指标",
                    synonyms=[""],
                    means=TermTarget(kind="metric", id="absent"),
                )
            ],
        }
    )
    assert metric_matches("未知问题", modified) == ()
    assert metric_matches("幽灵指标", modified) == ()


def test_occurrences_nfc_casefold_and_ascii_word_boundaries() -> None:
    """Unicode normalization preserves code-point positions while ASCII words stay whole."""
    request = AskRequest(question="Cafe\u0301 sales", reference_instant=REFERENCE)
    assert request.question == "Café sales"
    assert occurrences(request.question, "Café")[0].span() == (0, 4)
    assert occurrences("SALES versus salesforce", "sales")[0].span() == (0, 5)
    assert len(occurrences("SALES versus salesforce", "sales")) == 1
    assert occurrences("anything", " ") == []
