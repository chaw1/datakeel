# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Datasheet drafts, publication approval and optional metered worker execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.storage.database import DatasetRow, TaskRow
from datakeel.storage.dataset_service import list_versions
from datakeel.storage.datasheet_jobs import get_job
from datakeel.storage.datasheet_store import get_document, list_documents
from datakeel.storage.harness_service import list_traces
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from datakeel.actions.models import ActionPlan
    from datakeel.storage.database import Database
    from tests.actions.conftest import DatasetFixture


def _prepare(db: Database, dataset: DatasetFixture, **values: object) -> ActionPlan:
    dataset_id = dataset[0].id
    return prepare_action(
        db,
        "generate_datasheet",
        JsonDocument.model_validate(
            {"dataset_id": dataset_id, "version_id": list_versions(db, dataset_id)[0].id, **values}
        ),
    )


def _execute(db: Database, plan: ActionPlan) -> None:
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_template_generation_is_controlled_offline_and_idempotent(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """Draft creation needs no approval and a replay returns the exact existing document."""
    plan = _prepare(db, dataset)
    assert not plan.requires_approval
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    run = execute_plan(db, plan.id, request)
    assert run.status == "SUCCEEDED"
    assert execute_plan(db, plan.id, request).id == run.id
    documents = list_documents(db, dataset[0].id)
    assert len(documents) == 1
    assert len(documents[0].sections) == 7
    assert documents[0].sections[0].missing
    assert documents[0].published is False
    assert documents[0].mode == "template"
    assert all(
        sentence.fact_ids for section in documents[0].sections for sentence in section.sentences
    )
    assert list_traces(db, documents[0].id) == []


def test_publish_requires_real_approval_and_keeps_frozen_prose(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """A publication receipt cannot be produced without approving its exact draft digest."""
    _execute(db, _prepare(db, dataset))
    before = list_documents(db, dataset[0].id)[0]
    publish = prepare_action(
        db,
        "publish_datasheet",
        JsonDocument({"dataset_id": before.dataset_id, "document_id": before.id}),
    )
    assert publish.requires_approval
    with pytest.raises(AuthorizationError, match="human approval"):
        _execute(db, publish)
    assert not get_document(db, before.id).published
    approve_plan(db, publish.id, ApprovalDecision(approve=True, plan_digest=publish.plan_digest))
    _execute(db, publish)
    after = get_document(db, before.id)
    assert after.published
    assert after.facts == before.facts
    assert after.sections == before.sections


def test_external_model_plan_cannot_schedule_a_task_before_approval(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """Preparing and denying external generation never reads model keys or opens a client."""
    plan = _prepare(db, dataset, mode="model", provider="openai", model="gpt-4.1-mini")
    assert plan.external
    assert plan.requires_approval
    with pytest.raises(AuthorizationError, match="human approval"):
        _execute(db, plan)
    with db.session() as session:
        assert session.scalars(select(TaskRow)).all() == []
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    _execute(db, plan)
    assert get_job(db, plan.operation_id or plan.id).status == "QUEUED"
    assert list_documents(db, dataset[0].id) == ()


def test_model_provider_must_match_the_declared_price(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """A caller cannot mark a priced external model as the offline provider."""
    with pytest.raises(ValidationError, match="another provider"):
        _prepare(db, dataset, mode="model", provider="fake", model="gpt-4.1-mini")


def test_generation_rejects_changed_source_facts_after_preparation(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """The reviewed fact payload is bound to source values at controlled execution."""
    plan = _prepare(db, dataset)
    with db.session() as session:
        row = session.get(DatasetRow, dataset[0].id)
        assert row is not None
        row.metadata_values = {"owner": "Fixture Maintainer"}
        session.commit()
    with pytest.raises(ConflictError, match="state changed"):
        _execute(db, plan)
    assert list_documents(db, dataset[0].id) == ()


def test_model_worker_publishes_a_checked_document_without_creating_a_dataset_version(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """The offline model traverses real queue, budget and fence code without an SDK client."""
    before = list_versions(db, dataset[0].id)
    plan = _prepare(db, dataset, mode="model")
    _execute(db, plan)
    run_worker(db, once=True)
    job = get_job(db, plan.operation_id or plan.id)
    assert job.status == "COMPLETED", job.error
    assert job.document_id is not None
    document = get_document(db, job.document_id)
    assert document.mode == "model"
    assert len(document.sections) == 7
    assert any(section.sentences for section in document.sections)
    assert list_versions(db, dataset[0].id) == before
    traces = list_traces(db, job.id)
    assert len(traces) == 1
    assert traces[0].call_type == "extraction"
    assert traces[0].provider == "fake"
    assert traces[0].cost_usd == 0


def test_model_budget_rejection_produces_no_document_or_provider_trace(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """An exhausted token limit fails durably before calling even the fake provider."""
    plan = _prepare(db, dataset, mode="model", budget={"conversation_tokens": 0})
    _execute(db, plan)
    run_worker(db, once=True)
    job = get_job(db, plan.operation_id or plan.id)
    assert job.status == "FAILED"
    assert job.error is not None
    assert "BudgetError" in job.error
    assert list_documents(db, dataset[0].id) == ()
    assert list_traces(db, job.id) == []


def test_model_task_cannot_complete_without_its_checked_document(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """Generic queue completion cannot mark a documentation job successful without a document."""
    plan = _prepare(db, dataset, mode="model")
    _execute(db, plan)
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    with pytest.raises(ConflictError, match="checked completion"):
        queue.finish(lease, [], [])
    assert get_job(db, plan.operation_id or plan.id).status == "QUEUED"
    assert list_documents(db, dataset[0].id) == ()
