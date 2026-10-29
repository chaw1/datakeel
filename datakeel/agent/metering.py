# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve conversation context and model-turn accounting around routed attempts."""

from collections.abc import Callable
from functools import partial

from datakeel.agent.context import assemble
from datakeel.agent.demo import DemoProvider
from datakeel.agent.memory import workspace
from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import Conversation, ModelRequest, ModelResponse, Provider
from datakeel.core.memory_models import MemoryEntry, MemoryUseScope
from datakeel.core.routing_models import TierState
from datakeel.memory.service import reinforce_memories, select_memories
from datakeel.routing.accounting import CallContext, ModelAccount
from datakeel.routing.attempts import complete_with_fallback
from datakeel.routing.config import load_config
from datakeel.routing.tiers import model_chain, select_model
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_memory_sources import remember_memory_sources
from datakeel.storage.conversation_secrets import get_canary
from datakeel.storage.data_asset_context import project_agent_history
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import session_actor


class ModelMeter:
    """Meter one model node without inflating turns for its fallback attempts."""

    def __init__(
        self,
        db: Database,
        conversation_id: str,
        token: str,
        provider: Provider,
        accounting_conversation_id: str | None = None,
    ) -> None:
        """Keep response ownership outside framework configuration and checkpoint state."""
        self.db, self.conversation_id, self.token, self.provider = (
            db,
            conversation_id,
            token,
            provider,
        )
        self.accounting_conversation_id = accounting_conversation_id
        self.used_memory_ids: list[str] = []
        self._memory_ids: list[str] = []
        self._memory_entries: list[MemoryEntry] = []

    def complete(
        self,
        invoke: Callable[[ModelRequest], ModelResponse],
        *,
        has_plan: bool = False,
        has_tool_result: bool = False,
    ) -> ModelResponse:
        """Assemble unchanged context and count one turn when any provider was attempted."""
        conversation = memory.get(self.db, self.conversation_id)
        catalog = ToolCatalog(conversation)
        request = self._request(conversation, catalog)
        config = load_config()
        route = select_model(
            conversation.config,
            TierState(
                loaded_tools=list(catalog.loaded),
                response_has_plan=has_plan,
                response_has_tool_result=has_tool_result,
            ),
            config,
        )
        account = ModelAccount(
            self.db,
            CallContext(
                conversation_id=conversation.id,
                turn=conversation.turns + 1,
                provider=conversation.config.provider,
                limits=conversation.config.budget,
                input_divisor=4 if isinstance(self.provider, DemoProvider) else 1,
                accounting_conversation_id=self.accounting_conversation_id
                or conversation.root_conversation_id,
                agent_path=conversation.agent_path,
                depth=conversation.depth,
                parent_tool_call_id=conversation.parent_tool_call_id,
            ),
        )
        try:
            return complete_with_fallback(
                account,
                request,
                partial(self._invoke, invoke),
                route,
                model_chain(conversation.config, route, config),
                partial(self._request, conversation, catalog),
            )
        finally:
            if account.attempts:
                memory.append(self.db, self.conversation_id, self.token, model_call=True)

    def _invoke(
        self, invoke: Callable[[ModelRequest], ModelResponse], request: ModelRequest
    ) -> ModelResponse:
        remember_memory_sources(self.db, self.conversation_id, self.token, self._memory_entries)
        try:
            return invoke(request)
        finally:
            self.used_memory_ids = list(dict.fromkeys([*self.used_memory_ids, *self._memory_ids]))
            reinforce_memories(self.db, self._memory_ids, scope=self._memory_scope())

    def _memory_scope(self) -> MemoryUseScope:
        conversation = memory.get(self.db, self.conversation_id)
        root = memory.get(self.db, conversation.root_conversation_id or conversation.id)
        return MemoryUseScope(
            root_conversation_id=root.id,
            user_message_number=sum(
                message.role == "user" and message.name is None for message in root.messages
            ),
        )

    def _request(self, conversation: Conversation, catalog: ToolCatalog) -> ModelRequest:
        selected = select_memories(
            self.db,
            next(
                (
                    message.content
                    for message in reversed(conversation.messages)
                    if message.role == "user" and message.name is None
                ),
                "",
            ),
            conversation.config.dataset_id,
            actor=session_actor(self.db, self.conversation_id),
        )
        request = assemble(
            project_agent_history(self.db, conversation),
            catalog.core,
            list(catalog.loaded.values()),
            workspace(self.db, conversation),
            get_canary(self.db, self.conversation_id),
            selected.text,
        )
        request = request.model_copy(
            update={
                "agent_name": conversation.agent_name,
                "agent_path": conversation.agent_path,
            }
        )
        self._memory_ids = [entry.id for entry in selected.entries]
        self._memory_entries = selected.entries
        return request
