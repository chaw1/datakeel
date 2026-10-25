# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run each golden through the actual conversation and controlled-action services."""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import ValidationError as ModelValidationError

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.actions.service import list_runs
from datakeel.agent.models import AgentEvent
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import MessageInput
from datakeel.core.errors import DatakeelError
from datakeel.core.harness_eval import EvalCaseResult, GoldenCase, ObservedToolResult
from datakeel.harness.assessment import CaseObservation, assess
from datakeel.harness.cases import bind_case, seed_case
from datakeel.harness.operations import OperationObservation, apply_operation
from datakeel.harness.service import list_traces
from datakeel.memory.service import delete_memory, list_memories
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_files, list_versions
from datakeel.worker.runner import run_worker


def _run_turns(
    db: Database, case: GoldenCase, conversation_id: str, fake: FakeProvider | None
) -> tuple[list[AgentEvent], list[OperationObservation], list[ActionPlan]]:
    events: list[AgentEvent] = []
    operations: list[OperationObservation] = []
    plans: list[ActionPlan] = []
    for turn in case.turns:
        if turn.new_conversation:
            conversation_id = create_conversation(db, case.config).id
        if fake is not None:
            fake.script.extend(turn.script)
        for event in send_message(
            db, conversation_id, MessageInput(content=turn.input), provider=fake
        ):
            events.append(event)
            if (
                event.event == "plan"
                and event.outcome is not None
                and event.outcome.plan is not None
            ):
                plans.append(event.outcome.plan)
        operations.extend(
            apply_operation(db, plans[-1] if plans else None, operation)
            for operation in turn.operations
        )
        if turn.delete_memories:
            for entry in list_memories(db):
                delete_memory(db, entry.id)
    return events, operations, plans


def _version_outputs(db: Database, dataset_id: str, runs: list[ActionRun]) -> dict[str, list[str]]:
    identifiers = {
        ref.asset_id
        for run in runs
        if run.receipt is not None
        for ref in run.receipt.outputs
        if ref.asset_type == "version"
    }
    return {
        version.id: sorted(file.id for file in version.manifest)
        for version in list_versions(db, dataset_id)
        if version.id in identifiers
    }


def _measured_result(
    db: Database,
    case: GoldenCase,
    events: list[AgentEvent],
    operations: list[OperationObservation],
) -> EvalCaseResult:
    traces = list_traces(db)
    names = {item.name for item in case.expect.tool_results} | {
        item.selection_from_tool for item in case.expect.actions if item.selection_from_tool
    }
    return EvalCaseResult(
        id=case.id,
        passed=False,
        failures=[],
        tool_sequence=[
            event.call.name for event in events if event.event == "tool_call" and event.call
        ],
        action_types=[
            event.outcome.plan.action_type
            for event in events
            if event.event == "plan" and event.outcome and event.outcome.plan
        ],
        operations=[operation.status for operation in operations],
        final_answer=next(
            (event.text for event in reversed(events) if event.event == "text" and event.text), ""
        ),
        stop_reasons=[event.stop_reason for event in events if event.stop_reason],
        turns=sum(
            trace.call_type == "conversation"
            and trace.depth == 0
            and (trace.model_route is None or trace.model_route.attempt == 1)
            for trace in traces
        ),
        tokens=sum(trace.usage.input_tokens + trace.usage.output_tokens for trace in traces),
        cost_usd=sum((trace.cost_usd for trace in traces), start=Decimal(0)),
        tool_results=[
            ObservedToolResult(
                name=event.outcome.name,
                status=event.outcome.status,
                content=event.outcome.content,
                asset_refs=event.outcome.asset_refs,
            )
            for event in events
            if event.event == "tool_result" and event.outcome and event.outcome.name in names
        ],
        output_version_files=_version_outputs(db, case.config.dataset_id or "", list_runs(db)),
    )


def observe_case(db: Database, case: GoldenCase, fake: FakeProvider | None) -> CaseObservation:
    """Measure conversation activity separately from any actions used to prepare its fixture."""
    baseline_run_ids = {run.id for run in list_runs(db)}
    conversation = create_conversation(db, case.config)
    events, operations, plans = _run_turns(db, case, conversation.id, fake)
    if case.fixture_kind in {"kg", "image_kg"}:
        run_worker(db, once=True)
    memory = get_conversation(db, conversation.id)
    context = fake.requests[-1].messages if fake is not None and fake.requests else memory.messages
    files = list_files(db, case.config.dataset_id or "")
    return CaseObservation(
        result=_measured_result(db, case, events, operations),
        plans=plans,
        runs=[run for run in list_runs(db) if run.id not in baseline_run_ids],
        context="\n".join(message.content for message in context),
        operation_errors=[operation.error for operation in operations],
        file_count=len(files),
        quarantined_count=sum(file.metadata.get("quarantined") is True for file in files),
        memory_count=len(list_memories(db)),
        memory_used=bool(
            fake
            and fake.requests
            and any(segment.name == "memory" for segment in fake.requests[-1].segments)
        ),
    )


def _fixture_failure(case: GoldenCase, error: Exception) -> EvalCaseResult:
    description = f"Fixture extraction failed: {type(error).__name__}: {error}"
    return EvalCaseResult(
        id=case.id,
        passed=False,
        failures=[description],
        fixture_error=description,
        tool_sequence=[],
        action_types=[],
        operations=[],
        final_answer="",
        stop_reasons=["fixture_failure"],
        turns=0,
        tokens=0,
        cost_usd=Decimal(0),
    )


def run_case(case: GoldenCase, provider: Literal["fake", "openai", "anthropic"]) -> EvalCaseResult:
    """Isolate fixtures and budgets while exercising real runtime policy decisions."""
    with TemporaryDirectory(prefix="datakeel-golden-") as temporary:
        directory = Path(temporary)
        db = Database(f"sqlite:///{directory / 'case.db'}")
        db.migrate()
        try:
            try:
                case = bind_case(
                    case,
                    seed_case(db, directory, case.fixture_kind, reviewed=case.fixture_reviewed),
                )
            except (DatakeelError, ModelValidationError, OSError) as error:
                return _fixture_failure(case, error)
            model = {
                "fake": "fake-script",
                "openai": "gpt-4.1-mini",
                "anthropic": "claude-haiku-4-5-20251001",
            }[provider]
            case = case.model_copy(
                update={
                    "config": case.config.model_copy(
                        update={
                            "provider": provider,
                            "model": model,
                        }
                    )
                }
            )
            fake = FakeProvider([]) if provider == "fake" else None
            result = assess(case.expect, observe_case(db, case, fake))
            if fake is not None and fake.script_errors:
                result = result.model_copy(
                    update={"passed": False, "failures": [*result.failures, *fake.script_errors]}
                )
            return result
        finally:
            db.engine.dispose()
