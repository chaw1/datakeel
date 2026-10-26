# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Within-conversation memory and fresh controlled-action observations."""

from datakeel.agent.models import AgentEvent, ConversationView
from datakeel.core.agent_models import ChatMessage, Conversation
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage import conversation_store
from datakeel.storage.action_store import get_plan, list_runs
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_datasets


def conversation_view(db: Database, conversation: Conversation) -> ConversationView:
    """Refresh plan cards after UI approvals without rewriting historical evidence."""
    runs = list_runs(db)
    events: list[AgentEvent] = []
    for document in conversation.events:
        event = AgentEvent.model_validate(document.root)
        outcome = event.outcome
        if outcome is not None and outcome.plan is not None:
            plan = get_plan(db, outcome.plan.id)
            matching = [item for item in runs if item.plan_id == plan.id]
            run = next(
                (item for item in matching if item.status != "DENIED"),
                next(iter(matching), outcome.run),
            )
            outcome = outcome.model_copy(update={"plan": plan, "run": run})
            event = event.model_copy(update={"outcome": outcome})
        events.append(event)
    plans = {
        event.outcome.plan.id: event.outcome.plan
        for event in events
        if event.outcome is not None and event.outcome.plan is not None
    }
    return ConversationView(
        id=conversation.id,
        config=conversation.config,
        created_at=conversation.created_at,
        messages=conversation.messages,
        events=events,
        turns=conversation.turns,
        pending_plans=[plan for plan in plans.values() if plan.status in {"PREPARED", "APPROVED"}],
    )


def workspace(db: Database, conversation: Conversation) -> JsonDocument:
    """Append current asset identities and human decisions after stable context."""
    view = conversation_view(db, conversation)
    plans = {
        event.outcome.plan.id: event.outcome
        for event in view.events
        if event.outcome is not None and event.outcome.plan is not None
    }
    return JsonDocument.model_validate(
        {
            "dataset_id": conversation.config.dataset_id,
            "datasets": [{"id": dataset.id, "name": dataset.name} for dataset in list_datasets(db)],
            "plans": [_plan_summary(outcome).root for outcome in plans.values()],
            "dry_run": conversation.config.dry_run,
        }
    )


def _plan_summary(outcome: ToolOutcome) -> JsonDocument:
    """Keep current status concise while the transcript retains complete frozen plans."""
    plan, run = outcome.plan, outcome.run
    return JsonDocument.model_validate(
        {
            "plan_id": plan.id if plan else None,
            "action_type": plan.action_type if plan else None,
            "status": plan.status if plan else None,
            "requires_approval": plan.requires_approval if plan else False,
            "run": None
            if run is None
            else {
                "id": run.id,
                "status": run.status,
                "task_id": run.task_id,
                "has_receipt": run.receipt is not None,
            },
        }
    )


def close_interrupted(db: Database, conversation_id: str, token: str) -> None:
    """Complete abandoned tool exchanges and persist the recoverable stream boundary."""
    conversation = conversation_store.get(db, conversation_id)
    answered = {message.tool_call_id for message in conversation.messages if message.role == "tool"}
    for message in conversation.messages:
        for call in message.tool_calls:
            if call.id not in answered:
                conversation_store.append(
                    db,
                    conversation_id,
                    token,
                    message=ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        name=call.name,
                        content=ToolOutcome(
                            name=call.name, status="FAILED", error="interrupted"
                        ).model_dump_json(),
                    ),
                )
    for event in [AgentEvent(event="stopped", stop_reason="interrupted"), AgentEvent(event="done")]:
        conversation_store.append(
            db,
            conversation_id,
            token,
            event=JsonDocument.model_validate(event.model_dump(mode="json")),
        )
