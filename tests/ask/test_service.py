# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The full semantic pipeline produces independently verified answers and durable refusals."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from datakeel.ask import service
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.catalog_models import SourceProperties
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.errors import ExecutionError
from datakeel.core.models import JsonDocument
from datakeel.sample_enterprise import EnterpriseGold, EnterpriseSample
from datakeel.storage.ask_store import get_answer
from datakeel.storage.catalog_store import publish_snapshot, read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.metric_store import (
    get_metric,
    rollback_metric_in_session,
    update_metric_in_session,
)

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def test_all_twenty_benchmark_questions_match_independent_gold_and_replay(
    db: Database,
    enterprise_sample: EnterpriseSample,
) -> None:
    """Fourteen numeric answers, four refusals, and two clarifications retain complete evidence."""
    contract = yaml.safe_load(Path("contracts/ask/questions.yaml").read_text())
    gold = EnterpriseGold.model_validate_json(enterprise_sample.gold_path.read_text())
    for question in contract["questions"]:
        request = AskRequest(question=question["question"], reference_instant=REFERENCE)
        answer = ask_data(db, request)
        assert answer.status == question["expected_status"], question["id"]
        assert answer.assertion_ids, question["id"]
        assert answer.assertions, question["id"]
        assert get_answer(db, answer.id) == answer
        if answer.status == "answered":
            assert answer.metric_card is not None
            assert answer.metric_card.definition.id == question["metric_id"]
            assert answer.result is not None
            assert answer.result.rows[0][0] == pytest.approx(
                gold.answers[question["gold_key"]], rel=0.005
            )
            assert answer.sql is not None
            assert answer.sql.tables
            assert answer.sql.columns
            assert answer.matches
            assert answer.lineage is not None
        else:
            assert answer.result is None
            assert answer.sql is None
            assert len(answer.candidates) >= (3 if answer.status == "unanswerable" else 2)


def test_metric_change_and_rollback_change_question_answer_by_version(
    db: Database,
    enterprise_sample: EnterpriseSample,
) -> None:
    """Metric revisions change the same question and an inverse restores its former value."""
    request = AskRequest(question="上个季度华东区零售额是多少", reference_instant=REFERENCE)
    before = ask_data(db, request)
    card = get_metric(db, "retail_revenue")
    measure = card.definition.measure.model_copy(
        update={"column": "ecommerce/main/orders/list_amount"}
    )
    with db.session() as session:
        update_metric_in_session(session, card.definition.model_copy(update={"measure": measure}))
        session.commit()
    changed = ask_data(db, request)
    assert changed.metric_card is not None
    assert changed.metric_card.definition.version == 2
    assert changed.result != before.result
    with db.session() as session:
        rollback_metric_in_session(session, "retail_revenue", 1)
        session.commit()
    restored = ask_data(db, request)
    assert restored.result == before.result
    assert restored.metric_card is not None
    assert restored.metric_card.definition.version == 3


def test_grouped_question_returns_evidenced_table(
    db: Database,
    enterprise_sample: EnterpriseSample,
) -> None:
    """Registered dimension grouping produces a bounded result table from compiler SQL."""
    answer = ask_data(
        db, AskRequest(question="上个季度按零售区域零售额", reference_instant=REFERENCE)
    )
    assert answer.status == "answered"
    assert answer.result is not None
    assert answer.result.columns == ["region", "value"]
    assert len(answer.result.rows) == 4


def test_dimension_ambiguity_and_invalid_time_never_execute_sql(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported filters become persisted non-answers before source execution."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("A non-answer must never invoke SQL execution")

    monkeypatch.setattr(service, "execute_query", forbidden)
    for question, status in (
        ("华东和华南零售额", "clarification"),
        ("下个月零售额", "unanswerable"),
    ):
        answer = ask_data(db, AskRequest(question=question, reference_instant=REFERENCE))
        assert answer.status == status
        assert answer.sql is None


def test_source_failure_refuses_without_returning_partial_query_evidence(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An inaccessible source cannot turn into a fabricated numerical answer."""

    def failing(*_args: object, **_kwargs: object) -> None:
        msg = "Source unavailable"
        raise ExecutionError(msg)

    monkeypatch.setattr(service, "execute_query", failing)
    answer = ask_data(
        db, AskRequest(question="零售额", reference_instant=REFERENCE, session_id="reuse")
    )
    assert answer.status == "unanswerable"
    assert answer.result is None
    assert answer.sql is None
    assert answer.session_id == "reuse"


def test_source_lookup_rejects_missing_or_unsupported_connections(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing registration and unusable connection metadata both become durable refusals."""
    with db.session() as session:
        snapshot = read_snapshot(session)
    missing = snapshot.model_copy(
        update={
            "objects": tuple(
                item for item in snapshot.objects if item.asset_ref.asset_type != "source"
            )
        }
    )
    objects = tuple(
        item.model_copy(
            update={
                "properties": JsonDocument(
                    SourceProperties(
                        connection_url=None,
                        dialect="unsupported",
                    ).model_dump(mode="json")
                )
            }
        )
        if item.asset_ref.asset_id == "ecommerce"
        else item
        for item in snapshot.objects
    )
    unsupported = snapshot.model_copy(update={"objects": objects})
    for candidate in (missing, unsupported):
        monkeypatch.setattr(service, "read_snapshot", lambda _session, value=candidate: value)
        answer = ask_data(db, AskRequest(question="零售额", reference_instant=REFERENCE))
        assert answer.status == "unanswerable"
        assert answer.sql is None


def test_source_field_removal_refuses_before_execution_and_restore_recovers(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catalog changes refresh current resolution without manufacturing a new metric version."""
    with db.session() as session:
        original = next(
            snapshot
            for _, snapshot in snapshot_events(all_events(session))
            if snapshot.scope == "source:ecommerce"
        )
    missing = original.model_copy(
        update={
            "objects": tuple(
                item
                for item in original.objects
                if item.asset_ref.asset_id != "ecommerce/main/orders/paid_amount"
            )
        }
    )
    publish_snapshot(db, missing)
    execute = service.execute_query

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Unresolved metric must be refused before source execution")

    monkeypatch.setattr(service, "execute_query", forbidden)
    request = AskRequest(question="上个季度零售额", reference_instant=REFERENCE)
    refused = ask_data(db, request)
    assert refused.status == "unanswerable"
    assert refused.candidates[0].status == "unresolved"
    assert refused.sql is None
    assert refused.candidates[0].definition.version == 1
    publish_snapshot(db, original)
    monkeypatch.setattr(service, "execute_query", execute)
    restored = ask_data(db, request)
    assert restored.status == "answered"
    assert restored.metric_card is not None
    assert restored.metric_card.definition.version == 1
