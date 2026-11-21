# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Meter planner attempts with fallback routing and freshly recalled user notes."""

from functools import partial

from datakeel.core.agent_models import (
    ContextSegment,
    Conversation,
    ModelRequest,
    ModelResponse,
    Provider,
)
from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.memory_models import MemorySelection, MemoryUseScope
from datakeel.core.routing_models import TierState
from datakeel.intents.model_parse import AGENT_NAME
from datakeel.intents.planner import PlannerTurn
from datakeel.intents.scene import memory_text
from datakeel.memory.service import reinforce_memories, select_memories
from datakeel.routing.accounting import CallContext, ModelAccount
from datakeel.routing.attempts import complete_with_fallback
from datakeel.routing.config import load_config
from datakeel.routing.tiers import model_chain, select_model
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_memory_sources import remember_memory_sources
from datakeel.storage.database import Database


class PlannerCalls:
    """Keep every planner round on one routing and per-question memory boundary."""

    def __init__(
        self,
        db: Database,
        conversation: Conversation,
        provider: Provider,
        turn: PlannerTurn,
        token: str,
    ) -> None:
        """Bind billing and memory provenance to the conversation's current question."""
        self.db, self.conversation, self.provider = db, conversation, provider
        self.turn, self.lease = turn, token
        self.config = load_config()
        self.route = select_model(conversation.config, TierState(), self.config)
        self.used_memory_ids: list[str] = []
        self.selected = MemorySelection()
        self.account = ModelAccount(
            db,
            CallContext(
                conversation_id=conversation.id,
                turn=conversation.turns + 1,
                provider=conversation.config.provider,
                limits=conversation.config.budget,
                call_type="intent_classifier",
                agent_path=AGENT_NAME,
                accounting_conversation_id=conversation.root_conversation_id,
                depth=conversation.depth,
                parent_tool_call_id=conversation.parent_tool_call_id,
            ),
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Route all explore and repair rounds through independent settled attempts."""
        return complete_with_fallback(
            self.account,
            self._request(request),
            self._invoke,
            self.route,
            model_chain(self.conversation.config, self.route, self.config),
            partial(self._request, request),
        )

    def _request(self, request: ModelRequest) -> ModelRequest:
        # The planner retains pristine requests, including for look-ups and repairs.
        # Always append to that original so a deleted note cannot survive a retry.
        self.selected = select_memories(
            self.db,
            self.turn.text,
            self.turn.context.dataset_id,
            actor=self.turn.actor,
        )
        text = memory_text(self.selected.text)
        if not text:
            return request
        messages = [
            message.model_copy(update={"content": message.content + text})
            if message.name == "intent_context"
            else message
            for message in request.messages
        ]
        segment = ContextSegment(
            name="intent_memories", kind="volatile", text=text, tokens=estimate_tokens(text) + 16
        )
        return request.model_copy(
            update={"messages": messages, "segments": [*request.segments, segment]}
        )

    def _invoke(self, request: ModelRequest) -> ModelResponse:
        if self.lease:
            remember_memory_sources(
                self.db, self.conversation.id, self.lease, self.selected.entries
            )
        identifiers = [entry.id for entry in self.selected.entries]
        try:
            return self.provider.complete(request)
        finally:
            self.used_memory_ids = list(dict.fromkeys([*self.used_memory_ids, *identifiers]))
            if identifiers:
                reinforce_memories(self.db, identifiers, scope=self._memory_scope())

    def _memory_scope(self) -> MemoryUseScope:
        root = memory.get(self.db, self.conversation.root_conversation_id or self.conversation.id)
        return MemoryUseScope(
            root_conversation_id=root.id,
            user_message_number=sum(
                message.role == "user" and message.name is None for message in root.messages
            ),
        )
