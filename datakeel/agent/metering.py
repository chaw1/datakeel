# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve conversation context and model-turn accounting around routed attempts."""

from collections.abc import Callable

from datakeel.agent.context import assemble
from datakeel.agent.demo import DemoProvider
from datakeel.agent.memory import workspace
from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import ModelRequest, ModelResponse, Provider
from datakeel.core.routing_models import TierState
from datakeel.routing.accounting import CallContext, ModelAccount
from datakeel.routing.attempts import complete_with_fallback
from datakeel.routing.config import load_config
from datakeel.routing.tiers import model_chain, select_model
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_secrets import get_canary
from datakeel.storage.database import Database


class ModelMeter:
    """Meter one model node without inflating turns for its fallback attempts."""

    def __init__(self, db: Database, conversation_id: str, token: str, provider: Provider) -> None:
        """Keep response ownership outside framework configuration and checkpoint state."""
        self.db, self.conversation_id, self.token, self.provider = (
            db,
            conversation_id,
            token,
            provider,
        )

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
        request = assemble(
            conversation,
            catalog.core,
            list(catalog.loaded.values()),
            workspace(self.db, conversation),
            get_canary(self.db, self.conversation_id),
        )
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
            ),
        )
        try:
            return complete_with_fallback(
                account, request, invoke, route, model_chain(conversation.config, route, config)
            )
        finally:
            if account.attempts:
                memory.append(self.db, self.conversation_id, self.token, model_call=True)
