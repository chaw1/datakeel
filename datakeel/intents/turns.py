# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Let the Agent dialog hand a sentence to the planner before the free conversation.

Real providers get the full planner: rules first, then one metered model call. The offline
demo provider only uses the deterministic recipes. A scripted test provider opts in only
when its next scripted response is addressed to the ``intent_planner`` agent, so existing
scripts keep their exact behaviour.
"""

from typing import Literal

from datakeel.agent.demo import DemoProvider
from datakeel.agent.models import AgentEvent
from datakeel.agent.providers import FakeProvider
from datakeel.core.agent_models import ChatMessage, Conversation, Provider, ScriptedResponse
from datakeel.core.errors import DatakeelError
from datakeel.core.intent_models import IntentResult, PageContext
from datakeel.core.routing_models import TierState
from datakeel.intents.model_parse import AGENT_NAME
from datakeel.intents.planner import ModelAccess, PlannerTurn, conversation_focus, plan_turn
from datakeel.routing.accounting import CallContext, ModelAccount
from datakeel.routing.config import load_config
from datakeel.routing.tiers import select_model
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import session_actor

PlannerMode = Literal["off", "rules", "model"]


def planner_mode(provider: Provider, context: PageContext | None) -> PlannerMode:
    """Decide how much of the planner this provider may use.

    Only a message that carries page context (the Web Agent dialog always sends it) enters
    the planner, so API clients and existing conversations keep their exact behaviour.
    """
    if isinstance(provider, FakeProvider):
        head = provider.script[0] if provider.script else None
        engaged = isinstance(head, ScriptedResponse) and head.agent == AGENT_NAME
        return "model" if engaged else "off"
    if context is None:
        return "off"
    return "rules" if isinstance(provider, DemoProvider) else "model"


def pending_question(conversation: Conversation) -> IntentResult | None:
    """The previous turn's open question, if that turn ended with one."""
    for document in reversed(conversation.events):
        kind = document.root.get("event")
        if kind in {"done", "route"}:
            continue
        if kind != "intent":
            return None
        event = AgentEvent.model_validate(document.root)
        return event.intent if event.intent is not None and event.intent.kind == "clarify" else None
    return None


def _access(db: Database, conversation: Conversation) -> tuple[ModelAccount, ModelAccess]:
    selected = select_model(conversation.config, TierState(), load_config())
    account = ModelAccount(
        db,
        CallContext(
            conversation_id=conversation.id,
            turn=conversation.turns + 1,
            provider=conversation.config.provider,
            limits=conversation.config.budget,
            call_type="intent_classifier",
            agent_path=AGENT_NAME,
        ),
    )
    return account, ModelAccess(model=selected.model, allowed=True)


def planner_events(
    db: Database,
    conversation: Conversation,
    provider: Provider,
    context: PageContext | None,
    token: str,
) -> list[AgentEvent] | None:
    """Plan, answer, ask or refuse; None leaves the turn to the free conversation."""
    mode = planner_mode(provider, context)
    if mode == "off":
        return None
    text = next(item.content for item in reversed(conversation.messages) if item.role == "user")
    turn = PlannerTurn(
        text=text,
        actor=session_actor(db, conversation.id),
        conversation_id=conversation.id,
        context=context or PageContext(),
        pending=pending_question(conversation),
        focus=conversation_focus(db, conversation.id),
    )
    # The offline demo keeps its own disclosed vocabulary for questions; only recipes apply.
    rules_only = (None, ModelAccess(read_rules=False))
    account, access = _access(db, conversation) if mode == "model" else rules_only
    head = provider.script[0] if isinstance(provider, FakeProvider) and provider.script else None
    try:
        result = plan_turn(
            db,
            turn,
            complete=(lambda request: account.complete(request, provider.complete))
            if account
            else None,
            access=access,
        )
    except DatakeelError:
        result = None
    if (
        isinstance(provider, FakeProvider)
        and head is not None
        and provider.script
        and provider.script[0] is head
    ):
        # The rules answered without the model; drop the scripted planner response unused.
        provider.script.pop(0)
    if result is None:
        return None
    memory.append(
        db, conversation.id, token, message=ChatMessage(role="assistant", content=result.text)
    )
    return [AgentEvent(event="intent", intent=result, text=result.text, agent_name=AGENT_NAME)]
