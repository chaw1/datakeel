# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist delegation once, retain isolated child identity and enforce the parent's scope."""

from collections.abc import Callable
from time import perf_counter

from pydantic import ValidationError as ModelValidationError

from datakeel.actions.policy import digest
from datakeel.core.agent_models import ChatMessage, Conversation, ToolCall
from datakeel.core.canary import is_leak
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, DatakeelError
from datakeel.core.models import JsonDocument, new_id
from datakeel.delegation.loader import get_agent
from datakeel.delegation.models import (
    AgentDefinition,
    ChildResult,
    DelegateParams,
    DelegationResult,
)
from datakeel.delegation.policy import rejection
from datakeel.ontology.tool_models import ToolCallContext, ToolInvocationStart, ToolOutcome
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_asset_refs import conversation_asset_refs
from datakeel.storage.conversation_authorization import record_audit
from datakeel.storage.conversation_secrets import get_canary
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import bind_session_actor, session_actor
from datakeel.storage.tool_invocations import (
    begin_invocation,
    finish_invocation,
    invocation_identity,
    replay_invocation,
)

ChildRunner = Callable[[Conversation, str], ChildResult]


def _child(
    db: Database, parent: Conversation, definition: AgentDefinition, call: ToolCall
) -> Conversation:
    ordinal = 1 + sum(
        item.parent_conversation_id == parent.id and item.agent_name == definition.name
        for item in memory.list_all(db, include_children=True)
    )
    child = memory.store(
        db,
        Conversation(
            id=new_id(),
            config=parent.config.model_copy(update={"max_turns": definition.max_turns}),
            messages=[ChatMessage(role="system", content=definition.description)],
            parent_conversation_id=parent.id,
            root_conversation_id=parent.root_conversation_id or parent.id,
            agent_name=definition.name,
            agent_path=f"{parent.agent_path}/{definition.name}#{ordinal}",
            depth=parent.depth + 1,
            parent_tool_call_id=call.id,
            allowed_tools=definition.tools,
        ),
    )
    bind_session_actor(db, child.id, session_actor(db, parent.id))
    return child


def _cached(db: Database, outcome: ToolOutcome) -> DelegationResult:
    child_id = outcome.content.root.get("conversation_id")
    stop = outcome.content.root.get("stop_reason")
    if isinstance(child_id, str):
        refs = conversation_asset_refs(db, child_id)
        try:
            require_access(
                db,
                refs,
                AccessContext(actor=session_actor(db, child_id), entry="agent", scope="query"),
            )
        except AuthorizationError as error:
            return DelegationResult(
                outcome=ToolOutcome(name=outcome.name, status="FAILED", error=str(error))
            )
        outcome = outcome.model_copy(update={"asset_refs": list(refs)})
    return DelegationResult(
        outcome=outcome,
        events=memory.get(db, child_id).events if isinstance(child_id, str) else [],
        stop_reason=stop if isinstance(stop, str) else None,
    )


def _perform(
    db: Database, parent: Conversation, call: ToolCall, ordinal: int, run: ChildRunner
) -> DelegationResult:
    try:
        params = DelegateParams.model_validate(call.arguments.root)
        definition = get_agent(params.agent)
    except (DatakeelError, ModelValidationError) as error:
        return DelegationResult(
            outcome=ToolOutcome(name=call.name, status="FAILED", error=str(error))
        )
    reason = rejection(parent, definition, ordinal)
    if reason:
        record_audit(db, parent.id, "", "DELEGATION_DENIED", reason)
        return DelegationResult(outcome=ToolOutcome(name=call.name, status="FAILED", error=reason))
    child = _child(db, parent, definition, call)
    result = run(child, params.task)
    refs = conversation_asset_refs(db, child.id)
    try:
        require_access(
            db,
            refs,
            AccessContext(actor=session_actor(db, parent.id), entry="agent", scope="query"),
            record=False,
        )
    except AuthorizationError as error:
        return DelegationResult(
            outcome=ToolOutcome(name=call.name, status="FAILED", error=str(error))
        )
    if is_leak(get_canary(db, parent.id), result.summary) or result.stop_reason == "canary_leak":
        record_audit(db, parent.id, "", "CANARY_LEAK", "delegated_result")
        result = ChildResult(stop_reason="canary_leak")
    stop = result.stop_reason if result.stop_reason in {"canary_leak", "budget_exceeded"} else None
    return DelegationResult(
        **result.model_dump(exclude={"stop_reason"}),
        stop_reason=stop,
        outcome=ToolOutcome(
            name=call.name,
            status="FAILED" if result.stop_reason else "SUCCEEDED",
            error=result.stop_reason,
            asset_refs=list(refs),
            content=JsonDocument(
                {
                    "conversation_id": child.id,
                    "summary": result.summary,
                    "stop_reason": stop,
                }
            ),
        ),
    )


def delegate(
    db: Database, parent: Conversation, call: ToolCall, ordinal: int, run: ChildRunner
) -> DelegationResult:
    """Replay cached conclusions without starting a graph or reserving another model call."""
    identity = invocation_identity(parent.id, call.id)
    arguments_digest = digest(call.arguments.root)
    previous = replay_invocation(db, identity, call.name, arguments_digest)
    if previous is not None:
        return _cached(db, previous)
    started = perf_counter()
    identifier = begin_invocation(
        db,
        ToolInvocationStart(
            name=call.name,
            arguments_digest=arguments_digest,
            argument_keys=sorted(call.arguments.root),
            context=ToolCallContext(
                actor=session_actor(db, parent.id), session_id=parent.id, agent_id=parent.agent_path
            ),
            asset_refs=[],
            identifier=identity,
        ),
    )
    result = _perform(db, parent, call, ordinal, run)
    outcome = result.outcome.model_copy(update={"invocation_id": identifier})
    finish_invocation(db, outcome, (perf_counter() - started) * 1000)
    return result.model_copy(update={"outcome": outcome})
