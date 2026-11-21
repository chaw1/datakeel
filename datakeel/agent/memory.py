# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Within-conversation memory and fresh controlled-action observations."""

from collections.abc import Sequence

from datakeel.action_store.lifecycle import get_plans_by_ids, get_runs_by_plan_ids
from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.agent.models import AgentEvent, ConversationView
from datakeel.core.agent_models import ChatMessage, Conversation
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.dataset_store.dataset_service import list_datasets
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage import conversation_store
from datakeel.storage.database import Database
from datakeel.storage.intent_chains import get_chains_by_ids


def conversation_views(
    db: Database, conversations: Sequence[Conversation], *, include_chains: bool = True
) -> list[ConversationView]:
    """Refresh referenced cards together, retaining transcript and first-error order."""
    histories = [[AgentEvent.model_validate(item.root) for item in c.events] for c in conversations]
    events = [event for history in histories for event in history]
    plan_ids = sorted({e.outcome.plan.id for e in events if e.outcome and e.outcome.plan})
    plans = get_plans_by_ids(db, plan_ids)
    runs = {
        identifier: next(
            (run for run in matching if run.status != "DENIED"), next(iter(matching), None)
        )
        for identifier, matching in get_runs_by_plan_ids(db, plan_ids).items()
    }
    chains = get_chains_by_ids(
        db, [e.intent.chain.id for e in events if include_chains and e.intent and e.intent.chain]
    )
    views: list[ConversationView] = []
    for conversation, history in zip(conversations, histories, strict=True):
        for index in range(len(history)):
            event = history[index]
            if (outcome := event.outcome) is not None and outcome.plan is not None:
                if (plan := plans.get(outcome.plan.id)) is None:
                    msg = "Action plan not found"
                    raise NotFoundError(msg)
                outcome = outcome.model_copy(
                    update={"plan": plan, "run": runs[plan.id] or outcome.run}
                )
                event = event.model_copy(update={"outcome": outcome})
            if include_chains and (intent := event.intent) is not None and intent.chain is not None:
                if (chain := chains.get(intent.chain.id)) is None:
                    msg = "Action chain was not found"
                    raise NotFoundError(msg)
                event = event.model_copy(
                    update={"intent": intent.model_copy(update={"chain": chain})}
                )
            history[index] = event
        pending = {
            e.outcome.plan.id: e.outcome.plan for e in history if e.outcome and e.outcome.plan
        }
        views.append(
            ConversationView(
                id=conversation.id,
                config=conversation.config,
                created_at=conversation.created_at,
                messages=conversation.messages,
                events=history,
                turns=conversation.turns,
                pending_plans=[
                    plan for plan in pending.values() if plan.status in {"PREPARED", "APPROVED"}
                ],
            )
        )
    return views


def conversation_view(db: Database, conversation: Conversation) -> ConversationView:
    """Refresh one conversation through the same batched read path."""
    return conversation_views(db, [conversation])[0]


def workspace(db: Database, conversation: Conversation) -> JsonDocument:
    """Append current asset identities and human decisions after stable context."""
    view = conversation_views(db, [conversation], include_chains=False)[0]
    plans = {
        event.outcome.plan.id: (event.outcome.plan, event.outcome.run)
        for event in view.events
        if event.outcome is not None and event.outcome.plan is not None
    }
    return JsonDocument.model_validate(
        {
            "dataset_id": conversation.config.dataset_id,
            "datasets": [{"id": dataset.id, "name": dataset.name} for dataset in list_datasets(db)],
            "plans": [_plan_summary(plan, run).root for plan, run in plans.values()],
            "dry_run": conversation.config.dry_run,
        }
    )


def _plan_summary(plan: ActionPlan, run: ActionRun | None) -> JsonDocument:
    return JsonDocument(
        {
            "plan_id": plan.id,
            **plan.model_dump(mode="json", include={"action_type", "status"}),
            "requires_approval": plan.requires_approval,
            "run": None
            if run is None
            else {
                **run.model_dump(mode="json", include={"id", "status", "task_id"}),
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
