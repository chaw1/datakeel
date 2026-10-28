# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Answer and replay local business questions with registered semantic evidence."""

from fastapi import APIRouter, Request, Response

from datakeel.api.dependencies import DatabaseDependency
from datakeel.ask.access import answer_refs
from datakeel.ask.service import ask_data
from datakeel.core.ask_conversation_models import AskConversation
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.data_asset_models import AccessContext
from datakeel.storage import ask_conversations
from datakeel.storage.ask_store import get_answer
from datakeel.storage.data_asset_access import require_access, skip_protected

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("")
def ask(body: AskRequest, db: DatabaseDependency, request: Request) -> AskAnswer:
    """Resolve and execute a read-only registered metric, preserving its full evidence."""
    caller = _access(request, body.actor)
    return ask_data(db, body, access=caller)


def _access(request: Request, default: str = "local-user") -> AccessContext:
    return AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", default), entry="ask", scope="query"
    )


@router.post("/conversations")
def create_conversation(db: DatabaseDependency, request: Request) -> AskConversation:
    """Create a question thread independently of Agent runtime conversations."""
    return ask_conversations.create_conversation(db, actor=_access(request).actor)


@router.get("/conversations")
def list_conversations(db: DatabaseDependency, request: Request) -> list[AskConversation]:
    """List this actor's threads while omitting histories requiring absent grants."""
    caller = _access(request)
    conversations = ask_conversations.list_conversations(db, actor=caller.actor)
    entries = [
        (item.id, tuple(ref for answer in item.turns for ref in answer_refs(answer)))
        for item in conversations
    ]
    skipped = skip_protected(db, entries, caller)
    hidden: set[str] = set(skipped.ids) if skipped else set()
    return [item for item in conversations if item.id not in hidden]


@router.get("/conversations/{conversation_id}")
def open_conversation(
    conversation_id: str, db: DatabaseDependency, request: Request
) -> AskConversation:
    """Recover saved turns only after owner and current asset authorization checks."""
    caller = _access(request)
    conversation = ask_conversations.get_conversation(db, conversation_id, actor=caller.actor)
    require_access(
        db, tuple(ref for answer in conversation.turns for ref in answer_refs(answer)), caller
    )
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, db: DatabaseDependency, request: Request) -> Response:
    """Delete an owned thread and its persisted question history."""
    ask_conversations.delete_conversation(db, conversation_id, actor=_access(request).actor)
    return Response(status_code=204)


@router.get("/{answer_id}")
def replay(answer_id: str, db: DatabaseDependency, request: Request) -> AskAnswer:
    """Replay the saved result and original metric revision without rerunning SQL."""
    answer = get_answer(db, answer_id)
    caller = _access(request)
    if answer.conversation_id is not None:
        ask_conversations.get_conversation(db, answer.conversation_id, actor=caller.actor)
    require_access(db, answer_refs(answer), caller)
    return answer
