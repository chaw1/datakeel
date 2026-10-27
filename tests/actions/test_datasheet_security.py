# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Adversarial offline providers exercise approved facts, leases and durable billing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.agent_models import ModelRequest, ModelResponse, ToolCall
from datakeel.core.datasheet_execution import (
    DatasheetCompletion,
    DatasheetFence,
    DatasheetJob,
    DatasheetPrepared,
)
from datakeel.core.datasheet_models import DatasheetDocument
from datakeel.core.errors import ConflictError
from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.datasheets.templates import build_template
from datakeel.storage.budget_rows import BudgetReservationRow
from datakeel.storage.budget_service import reserve as reserve_budget
from datakeel.storage.dataset_service import list_versions
from datakeel.storage.datasheet_jobs import get_job, job_input
from datakeel.storage.datasheet_store import list_documents
from datakeel.storage.harness_service import list_traces
from datakeel.worker.datasheet_runner import execute_datasheet
from datakeel.worker.queue import DatabaseQueue, Lease

if TYPE_CHECKING:
    from datakeel.actions.models import ActionPlan
    from datakeel.core.agent_models import ConversationCreate
    from datakeel.core.harness_models import BudgetRequest, BudgetReservation
    from datakeel.core.harness_pricing import ModelPrice
    from datakeel.storage.database import Database
    from tests.actions.conftest import DatasetFixture


class FixtureProvider:
    """Record attempts while returning only injected results or an injected failure."""

    def __init__(self, response: ModelResponse, *, fail: bool = False) -> None:
        """Keep provider construction entirely independent of credential settings."""
        self.response, self.fail = response, fail
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Record the attempt before raising or returning the fixture response."""
        self.requests.append(request)
        if self.fail:
            msg = "Generated provider failure"
            raise RuntimeError(msg)
        return self.response


def _prepare(db: Database, dataset: DatasetFixture, **values: object) -> ActionPlan:
    return prepare_action(
        db,
        "generate_datasheet",
        JsonDocument.model_validate(
            {
                "dataset_id": dataset[0].id,
                "version_id": list_versions(db, dataset[0].id)[0].id,
                "mode": "model",
                **values,
            }
        ),
    )


def _schedule(db: Database, plan: ActionPlan) -> DatabaseQueue:
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    return DatabaseQueue(db, lease_seconds=0)


def _input(db: Database, lease: Lease) -> tuple[DatasheetJob, DatasheetPrepared]:
    return job_input(
        db,
        lease.datasheet_job_id or "",
        DatasheetFence(
            task_id=lease.task_id,
            shard_id=lease.shard_id,
            owner=lease.owner,
        ),
    )


def _response(prepared: DatasheetPrepared) -> ModelResponse:
    checked = build_template(prepared.facts)
    return ModelResponse(content=checked.model_dump_json(include={"sections"}))


def test_client_prepared_facts_and_model_destination_are_replaced_by_server(
    db: Database, dataset: DatasetFixture
) -> None:
    """Untrusted prepared objects cannot inject facts or alter the outgoing model config."""
    legitimate = _prepare(db, dataset)
    prepared = DatasheetPrepared.model_validate(legitimate.canonical_params["prepared"])
    forged = prepared.model_copy(
        update={
            "facts": tuple(
                fact.model_copy(update={"value": "Invented Fixture Company"})
                for fact in prepared.facts
            ),
            "target_url": "https://fixture.example.test/collect",
        }
    )
    plan = _prepare(db, dataset, prepared=forged.model_dump(mode="json"))
    actual = DatasheetPrepared.model_validate(plan.canonical_params["prepared"])
    assert actual.target_url is None
    assert "Invented Fixture Company" not in str(actual.facts)
    assert [(fact.id, fact.value) for fact in actual.facts] == [
        (fact.id, fact.value) for fact in prepared.facts
    ]


def test_model_failure_settles_unknown_usage_without_publishing_document(
    db: Database, dataset: DatasetFixture
) -> None:
    """Provider exceptions charge the conservative reservation exactly once and fail durably."""
    plan = _prepare(db, dataset)
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job, prepared = _input(db, lease)
    provider = FixtureProvider(_response(prepared), fail=True)
    assert execute_datasheet(queue, lease, provider)
    assert len(provider.requests) == 1
    assert get_job(db, job.id).status == "FAILED"
    assert list_documents(db, dataset[0].id) == ()
    traces = list_traces(db, job.id)
    assert len(traces) == 1
    assert traces[0].billing_status == "unknown"
    assert traces[0].accounted_tokens > 0
    with db.session() as session:
        assert {row.status for row in session.scalars(select(BudgetReservationRow))} == {"SETTLED"}


@pytest.mark.parametrize("failure", ["truncated", "tool_call", "budget_overrun"])
def test_paid_invalid_model_response_never_becomes_a_document(
    db: Database, dataset: DatasetFixture, failure: str
) -> None:
    """Retain the usage trace even when protocol validation or observed budget rejects output."""
    plan = _prepare(db, dataset)
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job, prepared = _input(db, lease)
    response = _response(prepared)
    if failure == "truncated":
        response = response.model_copy(update={"stop_reason": "length"})
    elif failure == "tool_call":
        response = response.model_copy(update={"tool_calls": [ToolCall(name="unused")]})
    else:
        response = response.model_copy(update={"usage": TokenUsage(input_tokens=1_000_001)})
    provider = FixtureProvider(response)
    assert execute_datasheet(queue, lease, provider)
    assert get_job(db, job.id).status == "FAILED"
    assert list_documents(db, dataset[0].id) == ()
    traces = list_traces(db, job.id)
    assert len(traces) == 1
    assert traces[0].budget_exceeded == (failure == "budget_overrun")


def test_destination_changed_after_approval_blocks_provider_and_budget(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The approved endpoint must still match before constructing an outbound completion."""
    plan = _prepare(db, dataset, provider="openai", model="gpt-4.1-mini")
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job, prepared = _input(db, lease)
    provider = FixtureProvider(_response(prepared))

    def changed_destination(_config: ConversationCreate) -> str:
        return "https://changed.example.test/v1"

    monkeypatch.setattr("datakeel.runtime.datasheet_model.model_destination", changed_destination)
    assert execute_datasheet(queue, lease, provider)
    assert provider.requests == []
    assert get_job(db, job.id).status == "FAILED"
    assert list_traces(db, job.id) == []
    with db.session() as session:
        assert session.scalars(select(BudgetReservationRow)).all() == []


def test_reaped_lease_cannot_invoke_provider_or_spend_budget(
    db: Database, dataset: DatasetFixture
) -> None:
    """A stale attempt loses outbound authorization before the final publication fence."""
    plan = _prepare(db, dataset)
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job, prepared = _input(db, lease)
    provider = FixtureProvider(_response(prepared))
    assert queue.reap() == 1
    assert not execute_datasheet(queue, lease, provider)
    assert provider.requests == []
    assert list_traces(db, job.id) == []
    assert list_documents(db, dataset[0].id) == ()


@pytest.mark.parametrize("tamper", ["identity", "facts", "language", "mode", "sections"])
def test_owned_completion_cannot_replace_frozen_document_identity_or_fact_values(
    db: Database, dataset: DatasetFixture, tamper: str
) -> None:
    """A valid queue lease authorizes only the document bound to its approved frozen facts."""
    plan = _prepare(db, dataset)
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job, prepared = _input(db, lease)
    checked = build_template(prepared.facts)
    document = DatasheetDocument(
        id=job.id,
        dataset_id=job.dataset_id,
        version_id=job.version_id,
        facts=prepared.facts,
        sections=checked.sections,
        mode="model",
    )
    alterations: dict[str, dict[str, object]] = {
        "identity": {"id": "forged-document"},
        "facts": {
            "facts": tuple(
                fact.model_copy(update={"value": "Invented value"}) for fact in prepared.facts
            )
        },
        "language": {"language": "en"},
        "mode": {"mode": "template"},
        "sections": {"sections": ()},
    }
    altered = alterations[tamper]
    document = document.model_copy(update=altered)
    with pytest.raises(ConflictError):
        queue.finish(lease, [], [], evidence=DatasheetCompletion(job_id=job.id, document=document))
    assert get_job(db, job.id).status == "QUEUED"
    assert list_documents(db, dataset[0].id) == ()


@pytest.mark.parametrize("mismatch", ["task", "shard", "owner", "job"])
def test_job_input_requires_exact_owned_lease_before_restoring_approved_payload(
    db: Database, dataset: DatasetFixture, mismatch: str
) -> None:
    """No worker can recover approved outbound facts using another attempt's identity."""
    plan = _prepare(db, dataset)
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job_id = lease.datasheet_job_id or ""
    fence = DatasheetFence(task_id=lease.task_id, shard_id=lease.shard_id, owner=lease.owner)
    if mismatch == "job":
        job_id = "other-job"
    else:
        field = {"task": "task_id", "shard": "shard_id", "owner": "owner"}[mismatch]
        fence = fence.model_copy(update={field: "other-identity"})
    with pytest.raises(ConflictError):
        job_input(db, job_id, fence)
    assert get_job(db, plan.operation_id or plan.id).status == "QUEUED"


def test_lease_lost_after_budget_reservation_is_refunded_without_model_invocation(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Close the reserve-to-provider gap and leave no unknown charge for an unmade call."""
    plan = _prepare(db, dataset)
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job, prepared = _input(db, lease)
    provider = FixtureProvider(_response(prepared))

    def reserve_then_cancel(
        database: Database, request: BudgetRequest, version: str, price: ModelPrice
    ) -> BudgetReservation:
        reservation = reserve_budget(database, request, version, price)
        assert queue.cancel(lease.task_id)
        return reservation

    monkeypatch.setattr("datakeel.runtime.datasheet_model.reserve", reserve_then_cancel)
    assert not execute_datasheet(queue, lease, provider)
    assert provider.requests == []
    assert get_job(db, job.id).status == "CANCELLED"
    assert list_traces(db, job.id) == []
    with db.session() as session:
        assert {row.status for row in session.scalars(select(BudgetReservationRow))} == {"REFUNDED"}


def test_cancellation_during_provider_call_keeps_billing_but_fences_document(
    db: Database, dataset: DatasetFixture
) -> None:
    """Already attempted completions remain accounted after their publication lease is lost."""
    plan = _prepare(db, dataset)
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job, prepared = _input(db, lease)

    class CancellingProvider(FixtureProvider):
        def complete(self, request: ModelRequest) -> ModelResponse:
            """Cancel only this fixture's task while its one model attempt is in flight."""
            assert queue.cancel(lease.task_id)
            return super().complete(request)

    provider = CancellingProvider(_response(prepared))
    assert not execute_datasheet(queue, lease, provider)
    assert len(provider.requests) == 1
    assert get_job(db, job.id).status == "CANCELLED"
    assert list_documents(db, dataset[0].id) == ()
    assert len(list_traces(db, job.id)) == 1
    with db.session() as session:
        assert {row.status for row in session.scalars(select(BudgetReservationRow))} == {"SETTLED"}


def test_replayed_model_output_keeps_supported_text_and_ledgers_four_fabrications(
    db: Database, dataset: DatasetFixture
) -> None:
    """A replayed provider response passes through the worker; only cited support survives."""
    plan = _prepare(db, dataset, language="en")
    queue = _schedule(db, plan)
    lease = queue.claim()
    assert lease is not None
    job, prepared = _input(db, lease)
    count = next(fact for fact in prepared.facts if fact.field == "manifest.file_count")
    supported = f"The dataset contains {count.value} files."
    proposals = [
        (supported, [count.id]),
        (f"The dataset contains {count.value}7 files.", [count.id]),
        ("Northwind Labs maintains the dataset.", [count.id]),
        (supported, ["fact-invented"]),
        (supported, []),
    ]
    content = json.dumps(
        {
            "sections": [
                {
                    "key": "composition",
                    "title": "Composition",
                    "sentences": [{"text": text, "fact_ids": ids} for text, ids in proposals],
                }
            ]
        }
    )
    assert execute_datasheet(queue, lease, FixtureProvider(ModelResponse(content=content)))
    assert get_job(db, job.id).status == "COMPLETED"
    (document,) = list_documents(db, dataset[0].id)
    kept = [sentence.text for section in document.sections for sentence in section.sentences]
    assert kept == [supported]
    assert [item.reasons for item in document.dropped_sentences] == [
        ("unsupported_number",),
        ("unsupported_term",),
        ("unknown_fact",),
        ("missing_citation",),
    ]
