# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent dialogue guards reject uncertain edits and preserve accepted query intent."""

from datetime import UTC, datetime

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def _ask(db: Database, question: str, previous: AskAnswer | None = None) -> AskAnswer:
    return ask_data(
        db,
        AskRequest(
            question=question,
            reference_instant=REFERENCE,
            conversation_id=previous.conversation_id if previous else None,
        ),
    )


def test_followup_conflicting_comparisons_require_clarification(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Two distinct comparison requests cannot silently select whichever rule runs last."""
    first = _ask(db, "上个月华东零售额")
    assert first.status == "answered"
    answer = _ask(db, "同比,环比", first)
    assert answer.status == "clarification"
    assert answer.result is None
    assert answer.comparison is None
    assert answer.interpreted_question


def test_followup_conflicting_time_grains_require_clarification(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A chart cannot present a guessed granularity for an unresolved choice of buckets."""
    first = _ask(db, "last quarter retail revenue")
    answer = _ask(db, "by month, by quarter", first)
    assert answer.status == "clarification"
    assert answer.result is None
    assert answer.sql is None


def test_clarification_does_not_commit_unaccepted_comparison_to_next_turn(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A comparison refused for missing dates must not reappear after an unrelated edit."""
    first = _ask(db, "零售额")
    assert first.status == "answered"
    refused = _ask(db, "同比", first)
    assert refused.status == "clarification"
    assert refused.result is None
    answer = _ask(db, "上个月呢", refused)
    complete = _ask(db, "上个月零售额")
    assert answer.status == complete.status == "answered"
    assert answer.result == complete.result
    assert answer.query_frame == complete.query_frame
    assert answer.comparison is None


def test_metric_switch_maps_the_same_business_dimension_across_registered_sources(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Changing metric keeps the requested business region even when its contract ID changes."""
    first = _ask(db, "上个季度华东零售额")
    answer = _ask(db, "换成销售额", first)
    complete = _ask(db, "上个季度华东销售额")
    assert answer.status == complete.status == "answered"
    assert answer.result == complete.result
    assert answer.query_frame == complete.query_frame
    assert answer.query_frame is not None
    assert answer.query_frame.slices[0].dimension_id == "sales_region"


def test_unknown_followup_clause_does_not_commit_a_partially_understood_region_edit(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A recognized region next to an unknown condition never becomes a hidden default."""
    first = _ask(db, "last quarter retail revenue in East China")
    refused = _ask(db, "what about South China with lunar visibility only", first)
    assert refused.status == "clarification"
    assert refused.result is None
    answer = _ask(db, "by month", refused)
    complete = _ask(db, "last quarter retail revenue in East China by month")
    assert answer.status == complete.status == "answered"
    assert answer.result == complete.result
    assert answer.query_frame == complete.query_frame


def test_multiple_region_values_and_negation_never_guess_a_single_slice(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Neither alternatives nor unsupported exclusions may collapse to one selected value."""
    first = _ask(db, "上个季度华东零售额")
    alternatives = _ask(db, "what about South China and North China", first)
    assert alternatives.status == "clarification"
    assert alternatives.result is None
    excluded = _ask(db, "excluding East China", alternatives)
    assert excluded.status == "clarification"
    assert excluded.result is None
    answer = _ask(db, "上个月呢", excluded)
    complete = _ask(db, "上个月华东零售额")
    assert answer.status == complete.status == "answered"
    assert answer.result == complete.result


def test_new_question_clears_prior_comparison_time_grain_and_region(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A fully expressed new topic resets every inherited slot, including chart buckets."""
    first = _ask(db, "上个季度华南零售额按月同比")
    assert first.status == "answered"
    assert first.comparison is not None
    answer = _ask(db, "上个月华东订单数是多少", first)
    complete = _ask(db, "上个月华东订单数是多少")
    assert answer.status == complete.status == "answered"
    assert answer.result == complete.result
    assert answer.query_frame == complete.query_frame
    assert answer.comparison is None


def test_incompatible_metric_switch_clarifies_without_losing_the_last_accepted_frame(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A new metric without an equivalent channel cannot drop the old channel silently."""
    first = _ask(db, "上个季度线上零售额")
    assert first.status == "answered"
    refused = _ask(db, "换成库存量", first)
    assert refused.status == "clarification"
    assert refused.result is None
    answer = _ask(db, "上个月呢", refused)
    complete = _ask(db, "上个月线上零售额")
    assert answer.status == complete.status == "answered"
    assert answer.result == complete.result
    assert answer.query_frame == complete.query_frame


def test_metric_followup_marker_preserves_region_and_time_without_explicit_switch_word(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """An elliptical metric question is an edit, while a complete question resets context."""
    first = _ask(db, "上个季度华南零售额")
    answer = _ask(db, "那订单数呢", first)
    complete = _ask(db, "上个季度华南订单数")
    assert answer.status == complete.status == "answered"
    assert answer.result == complete.result
    assert answer.query_frame == complete.query_frame
    english = _ask(db, "what about retail revenue", answer)
    original = _ask(db, "上个季度华南零售额")
    assert english.status == original.status == "answered"
    assert english.result == original.result
    assert english.query_frame == original.query_frame


def test_complete_new_question_with_polite_particle_resets_prior_slots(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A terminal question particle cannot turn a fully specified new topic into an edit."""
    first = _ask(db, "去年华南零售额按月同比")
    assert first.status == "answered"
    answer = _ask(db, "上个月华东订单数是多少呢", first)
    complete = _ask(db, "上个月华东订单数是多少呢")
    assert answer.status == complete.status == "answered"
    assert answer.result == complete.result
    assert answer.query_frame == complete.query_frame
    assert answer.comparison is None
