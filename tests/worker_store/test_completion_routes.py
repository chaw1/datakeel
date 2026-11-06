# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every stored association routes exactly once, with no untyped completion escape."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from datakeel.core.datasheet_execution import DatasheetCompletion
from datakeel.core.datasheet_models import DatasheetDocument
from datakeel.core.dq_models import DqResult
from datakeel.core.dq_monitor import DqCompletion
from datakeel.core.errors import ConflictError
from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_execution import PendingExtraction
from datakeel.core.kg_execution import KGCompletion, KGRun
from datakeel.core.kg_product import ProductExtraction
from datakeel.core.models import LineageEvent, utcnow
from datakeel.persistence.task_completion import BoundTaskCompletion
from datakeel.worker_store.completion import CompletionRequest, CompletionResult

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.worker_store.completion import CompletionPayload


def payloads() -> tuple[KGCompletion, DqCompletion, DatasheetCompletion]:
    """Provide generated products without model providers, storage rows or external sources."""
    return (
        KGCompletion(
            run=KGRun(
                id="kg",
                dataset_id="dataset",
                version_id="version",
                schema_id="schema",
                profile_id="fake",
                model="fake",
                extractor="fake",
                status="completed",
                created_at=utcnow(),
            ),
            products=ProductExtraction(),
        ),
        DqCompletion(run_id="dq", result=DqResult(rule_id="rule", status="passed")),
        DatasheetCompletion(
            job_id="sheet",
            document=DatasheetDocument(
                dataset_id="dataset",
                version_id="version",
                facts=(),
                sections=(),
                mode="model",
            ),
        ),
    )


def request(payload: CompletionPayload = ()) -> CompletionRequest:
    """Build a row-free request with stable generated task identity."""
    return CompletionRequest(task_id="task", dataset_id="dataset", created_at=100, payload=payload)


def rejection(port: BoundTaskCompletion, value: CompletionRequest) -> str | None:
    """Return the observed rejection so mutation kills require an actual assertion."""
    try:
        port.complete(value)
    except ConflictError as error:
        return str(error)
    return None


def test_typed_completion_models_are_frozen_and_forbid_extra() -> None:
    """Neither boundary accepts a Session/Row side channel or permits field replacement."""
    for model in (request(), CompletionResult(operator="pipeline.complete")):
        assert model.model_config["frozen"]
        assert model.model_config["extra"] == "forbid"
        with pytest.raises(ValidationError, match="frozen"):
            model.operator = "changed"
        with pytest.raises(ValidationError, match="extra_forbidden"):
            type(model).model_validate({**model.model_dump(), "session": object()})
    with pytest.raises(ValidationError):
        CompletionRequest.model_validate({**request().model_dump(), "payload": {"unknown": True}})


def test_duplicate_and_empty_associations_fail_closed(db: Database) -> None:
    """No success, failure or cancellation can choose among multiple persisted associations."""
    with db.session() as session:
        port = BoundTaskCompletion(session)
        for phase in ("publish", "FAILED", "CANCELLED"):
            for values in (
                {"kg_run_id": "kg", "dq_run_id": "dq"},
                {"dq_run_id": "dq", "datasheet_job_id": "sheet"},
                {"kg_run_id": "kg", "datasheet_job_id": "sheet"},
                {"kg_run_id": ""},
                {"dq_run_id": ""},
                {"datasheet_job_id": ""},
            ):
                value = request().model_copy(update={**values, "phase": phase, "error": "failed"})
                assert (
                    rejection(port, value) == "Task completion has ambiguous or empty associations"
                )


def test_missing_association_rejects_every_domain_payload(db: Database) -> None:
    """Typed products cannot be accepted as ordinary pipeline evidence without a stored link."""
    with db.session() as session:
        port = BoundTaskCompletion(session)
        for payload in payloads():
            for phase in ("publish", "FAILED", "CANCELLED"):
                assert rejection(port, request(payload).model_copy(update={"phase": phase})) == (
                    "Task completion payload has no matching association"
                )


def test_mismatched_or_missing_product_rejected_for_each_route(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful domain tasks require their exact product type and associated identity."""
    for handler in ("publish_kg", "publish_dq", "publish_datasheet"):
        monkeypatch.setattr(f"datakeel.persistence.task_completion.{handler}", lambda *_args: None)
    products = payloads()
    with db.session() as session:
        port = BoundTaskCompletion(session)
        for field, identity, correct in zip(
            ("kg_run_id", "dq_run_id", "datasheet_job_id"),
            ("kg", "dq", "sheet"),
            products,
            strict=True,
        ):
            for phase in ("publish", "FAILED", "CANCELLED"):
                for payload in ((), *products):
                    value = request(payload).model_copy(update={field: identity, "phase": phase})
                    if payload != correct and (payload != () or phase == "publish"):
                        assert rejection(port, value) is not None
                wrong = request(correct).model_copy(update={field: "other", "phase": phase})
                assert rejection(port, wrong) is not None


def install_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, tuple[object, ...], dict[str, object]]]:
    """Observe only the explicit handler boundary while leaving routing real."""
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
    for name in (
        "publish_kg",
        "publish_dq",
        "publish_datasheet",
        "fail_kg",
        "fail_dq",
        "fail_datasheet",
        "record_extraction_in_session",
    ):

        def record(*args: object, _name: str = name, **kwargs: object) -> None:
            calls.append((_name, args, kwargs))

        monkeypatch.setattr(f"datakeel.persistence.task_completion.{name}", record)
    return calls


def test_each_product_routes_once_and_terminal_failure_keeps_attribution(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adapters use the bound session, never commit, and preserve terminal metadata and defaults."""
    calls = install_handlers(monkeypatch)
    evidence = PendingExtraction(
        event=LineageEvent(idempotency_key="evidence", operator="example", event_type="COMPLETE"),
        bundle=KnowledgeBundle(run_id="evidence", assertions=()),
    )
    with db.session() as session:
        port = BoundTaskCompletion(session)
        for field, payload, publisher, failure, operator, fallback in zip(
            ("kg_run_id", "dq_run_id", "datasheet_job_id"),
            payloads(),
            ("publish_kg", "publish_dq", "publish_datasheet"),
            ("fail_kg", "fail_dq", "fail_datasheet"),
            ("kg.complete", "dq.complete", "datasheet.complete"),
            ("Graph task cancelled", "Quality task cancelled", "Datasheet task cancelled"),
            strict=True,
        ):
            identity = {"kg_run_id": "kg", "dq_run_id": "dq", "datasheet_job_id": "sheet"}[field]
            value = request(payload).model_copy(update={field: identity})
            result = port.complete(value)
            assert calls[-1] == (publisher, (session, payload, "task"), {})
            before = len(calls)
            assert port.complete(value.model_copy(update={"phase": "COMPLETED"})) == result
            assert len(calls) == before
            assert result.operator == operator
            assert not result.publish_version
            assert result.display_name == (
                "Datasheet generation" if field == "datasheet_job_id" else "Pipeline run"
            )
            for phase in ("FAILED", "CANCELLED"):
                failed = value.model_copy(update={"payload": (), "phase": phase})
                assert port.complete(failed) == result
                name, args, kwargs = calls[-1]
                assert name == failure
                assert args == (session, identity, fallback)
                if field != "kg_run_id":
                    assert kwargs["cancelled"] == (phase == "CANCELLED")
                if field == "dq_run_id":
                    assert kwargs["started_at"].timestamp() == 100
        result = port.complete(request((evidence,)))
        assert calls[-1] == (
            "record_extraction_in_session",
            (session, evidence.event, evidence.bundle),
            {},
        )
        assert result == CompletionResult(operator="pipeline.complete", publish_version=True)
        assert len(calls) == 10
