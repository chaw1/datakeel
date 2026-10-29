# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Ordinary article-bearing relative years remain standalone temporal questions."""

from datetime import UTC, datetime

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_conversations import get_conversation
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def test_last_year_with_article_matches_the_equivalent_complete_calendar_question(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """The comparison extension retains P12's existing English period semantics."""
    complete = ask_data(db, AskRequest(question="2025年零售额", reference_instant=REFERENCE))
    assert complete.status == "answered"
    for lead in ("in", "for", "over"):
        answer = ask_data(
            db,
            AskRequest(
                question=f"retail revenue {lead} the last year", reference_instant=REFERENCE
            ),
        )
        assert answer.status == "answered", (lead, answer.message)
        assert answer.result == complete.result
        assert answer.query_frame == complete.query_frame
        assert answer.comparison is None


def test_interpreted_question_uses_contract_labels_and_preserves_every_query_slot(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """The persisted explanation names business dimensions instead of storage identities."""
    answer = ask_data(
        db,
        AskRequest(question="上个季度华东零售额按零售渠道按月同比", reference_instant=REFERENCE),
    )
    assert answer.status == "answered"
    text = answer.interpreted_question
    assert "零售额" in text
    assert "2026-07-01" in text
    assert "2026-10-01" in text
    assert "零售区域为华东" in text
    assert "按零售渠道分组" in text
    assert "按月拆分" in text
    assert "与去年同期比较" in text
    assert "retail_region" not in text
    assert "retail_channel" not in text
    assert answer.conversation_id
    restored = get_conversation(db, answer.conversation_id)
    assert restored.turns[0].interpreted_question == text
