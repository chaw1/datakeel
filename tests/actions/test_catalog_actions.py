# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled metadata changes preserve events, versions, and legacy file boundaries."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from datakeel.actions.catalog_parameters import ImportCatalogParams
from datakeel.actions.models import ActionContext, ActionRun, ExecuteRequest
from datakeel.actions.registry import action_definition
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.catalog_models import CatalogImportRequest, CatalogSnapshot
from datakeel.core.errors import BudgetError, ConflictError, NotFoundError, ValidationError
from datakeel.core.metric_models import (
    Measure,
    MetricDefinition,
    MetricTime,
    SemanticLayer,
    TermDefinition,
    TermTarget,
)
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_queries import read_objects
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.metric_store import get_metric, install_layer, metric_history_detail
from datakeel.storage.term_changes import current_term


def _execute(db: Database, action: str, params: JsonDocument) -> ActionRun:
    plan = prepare_action(db, action, params, ActionContext(actor="catalog-editor"))
    assert plan.manifest.objects == []
    assert plan.reversible
    assert not plan.requires_approval
    return execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="catalog-editor")
    )


@pytest.fixture
def request_params(tmp_path: Path) -> JsonDocument:
    """Create a tiny local source and report one malformed external SQL statement."""
    source = tmp_path / "catalog.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE orders(amount INTEGER, quantity INTEGER, date TEXT)")
        connection.execute("INSERT INTO orders VALUES (100, 2, '2026-08-01')")
    invalid = tmp_path / "broken.sql"
    invalid.write_text("SELECT (((;")
    return JsonDocument(
        ImportCatalogParams(
            request=CatalogImportRequest(
                source_id="test",
                name="Generated",
                connection_url=f"sqlite:///{source}",
                sql_files=(str(invalid),),
            ),
            snapshot=CatalogSnapshot(scope="caller-supplied-must-be-ignored"),
        ).model_dump(mode="json")
    )


@pytest.fixture
def semantic(db: Database, request_params: JsonDocument) -> MetricDefinition:
    """Register a small semantic layer on a controlled source import."""
    _execute(db, "import_catalog", request_params)
    metric = MetricDefinition(
        id="revenue",
        name="零售额",
        description="Generated",
        owner="Retail",
        measure=Measure(
            table="test/main/orders", column="test/main/orders/amount", aggregation="sum"
        ),
        time=MetricTime(column="test/main/orders/date"),
    )
    install_layer(
        db,
        SemanticLayer(
            metrics=[metric],
            terms=[TermDefinition(term="零售额", means=TermTarget(kind="metric", id="revenue"))],
        ),
    )
    return metric


def test_explicit_repeat_import_is_event_free(db: Database, request_params: JsonDocument) -> None:
    """A second prepare and execute retains a receipt but appends no lineage event."""
    first = _execute(db, "import_catalog", request_params)
    assert first.receipt is not None
    with db.session() as session:
        count = len(all_events(session))
        assert read_snapshot(session).objects
    second = _execute(db, "import_catalog", request_params)
    assert second.receipt is not None
    details = second.receipt.quality["details"]
    assert isinstance(details, dict)
    assert details["status"] == "unchanged"
    report = details["report"]
    assert isinstance(report, dict)
    assert report["failed_sql_count"] == 1
    assert report["parse_failures"]
    assert report["unchanged"] == report["object_count"]
    with db.session() as session:
        assert len(all_events(session)) == count


def test_import_inverse_restores_prior_snapshot(db: Database, request_params: JsonDocument) -> None:
    """Undoing the initial import publishes an empty source version without deleting events."""
    _execute(db, "import_catalog", request_params)
    assert action_definition("import_catalog").inverse_of == "restore_catalog"
    _execute(db, "restore_catalog", JsonDocument({"scope": "source:test", "version": 0}))
    assert read_objects(db).total == 0
    _execute(db, "restore_catalog", JsonDocument({"scope": "source:test", "version": 1}))
    assert read_objects(db).total == 5
    with pytest.raises(NotFoundError, match="snapshot not found"):
        _execute(db, "restore_catalog", JsonDocument({"scope": "source:test", "version": 99}))


def test_metric_change_and_inverse_are_attributable(
    db: Database, semantic: MetricDefinition
) -> None:
    """Replacements and rollback create monotonically increasing versions and explicit audit."""
    changed = semantic.model_copy(
        update={
            "measure": semantic.measure.model_copy(update={"column": "test/main/orders/quantity"})
        }
    )
    first = _execute(
        db, "update_metric", JsonDocument({"definition": changed.model_dump(mode="json")})
    )
    assert get_metric(db, "revenue").definition.version == 2
    assert "semantic_change" in action_definition("update_metric").effects
    inverse = action_definition("update_metric").inverse_of
    assert inverse == "rollback_metric"
    second = _execute(db, inverse, JsonDocument({"metric_id": "revenue", "version": 1}))
    restored = get_metric(db, "revenue").definition
    assert restored.version == 3
    assert restored.measure == semantic.measure
    history = metric_history_detail(db, "revenue")
    assert [card.definition.version for card in history.versions] == [1, 2, 3]
    assert [(item.from_version, item.to_version) for item in history.audit] == [(1, 2), (2, 3)]
    assert {item.plan_id for item in history.audit} == {first.plan_id, second.plan_id}
    assert all(item.actor == "catalog-editor" and item.event_id for item in history.audit)


def test_intervening_semantic_change_invalidates_plan(
    db: Database, semantic: MetricDefinition
) -> None:
    """A prepared change cannot overwrite another committed semantic version."""
    params = JsonDocument(
        {"definition": semantic.model_copy(update={"owner": "New"}).model_dump(mode="json")}
    )
    plan = prepare_action(db, "update_metric", params)
    _execute(db, "update_metric", params)
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    with pytest.raises(ConflictError, match="Expected metric version"):
        _execute(db, "update_metric", params)
    with pytest.raises(NotFoundError, match="revision not found"):
        _execute(db, "rollback_metric", JsonDocument({"metric_id": "revenue", "version": 99}))


def test_term_update_and_rollback_keep_versions(db: Database, semantic: MetricDefinition) -> None:
    """Glossary rollback restores meaning as a new authoritative catalog revision."""
    definition = TermDefinition(
        term="零售额", synonyms=["终端销售"], means=TermTarget(kind="metric", id=semantic.id)
    )
    params = JsonDocument(
        {"definition": definition.model_dump(mode="json"), "expected_revision": 1}
    )
    _execute(db, "update_term", params)
    with pytest.raises(ConflictError, match="Expected term revision"):
        _execute(db, "update_term", params)
    _execute(db, "rollback_term", JsonDocument({"term": "零售额", "revision": 1}))
    with db.session() as session:
        current = current_term(session, "零售额")
        assert current.revision == 3
        assert current.properties.root["synonyms"] == []
    with pytest.raises(NotFoundError, match="revision not found"):
        _execute(db, "rollback_term", JsonDocument({"term": "零售额", "revision": 99}))
    with pytest.raises(NotFoundError, match="Term not found"):
        _execute(
            db,
            "update_term",
            JsonDocument(
                {
                    "definition": definition.model_copy(update={"term": "missing"}).model_dump(
                        mode="json"
                    ),
                    "expected_revision": 1,
                }
            ),
        )


def test_controlled_metric_update_changes_answer_and_inverse_restores_gold(
    db: Database, semantic: MetricDefinition
) -> None:
    """Exercise D8 through actual plans, query execution, evidence publication, and audit."""
    question = AskRequest(
        question="上个季度零售额", reference_instant=datetime(2026, 10, 1, tzinfo=UTC)
    )
    original = ask_data(db, question)
    assert original.result is not None
    assert original.result.rows == [[100]]
    changed = semantic.model_copy(
        update={
            "measure": semantic.measure.model_copy(update={"column": "test/main/orders/quantity"})
        }
    )
    _execute(db, "update_metric", JsonDocument({"definition": changed.model_dump(mode="json")}))
    after = ask_data(db, question)
    assert after.metric_card is not None
    assert after.metric_card.definition.version == 2
    assert after.result is not None
    assert after.result.rows == [[2]]
    inverse = action_definition("update_metric").inverse_of
    assert inverse is not None
    _execute(db, inverse, JsonDocument({"metric_id": "revenue", "version": 1}))
    restored = ask_data(db, question)
    assert restored.result == original.result
    assert restored.metric_card is not None
    assert restored.metric_card.definition.version == 3
    assert len(metric_history_detail(db, "revenue").audit) == 2


@pytest.mark.parametrize("target", ["missing", "test/main/orders"])
def test_term_target_must_exist_with_declared_kind(
    db: Database, semantic: MetricDefinition, target: str
) -> None:
    """Reject absent targets and a real table falsely identified as a metric."""
    definition = TermDefinition(term="零售额", means=TermTarget(kind="metric", id=target))
    with pytest.raises(ValidationError, match="not registered"):
        _execute(
            db,
            "update_term",
            JsonDocument(
                {"definition": definition.model_dump(mode="json"), "expected_revision": 1}
            ),
        )
    with db.session() as session:
        assert current_term(session, "零售额").revision == 1
        assert not any(event.operator == "TERM_CHANGE" for event in all_events(session))
    assert semantic.version == 1


def test_restoration_impact_counts_source_objects_and_enforces_budget(
    db: Database, request_params: JsonDocument
) -> None:
    """Restoring an empty version cannot hide the affected source behind a one-object count."""
    _execute(db, "import_catalog", request_params)
    params = JsonDocument({"scope": "source:test", "version": 0})
    with pytest.raises(BudgetError, match="impact exceeds"):
        prepare_action(db, "restore_catalog", params, ActionContext(max_objects=1))
    plan = prepare_action(db, "restore_catalog", params)
    assert plan.impact.object_count == 5
    assert not plan.manifest.objects
