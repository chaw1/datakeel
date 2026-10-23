# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Translate typed model boundaries without changing prompt or usage accounting."""

from collections.abc import Sequence

from anthropic import AnthropicError
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.ai import InputTokenDetails, UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from openai import OpenAIError
from pydantic import PrivateAttr

from datakeel.core.agent_models import ChatMessage, ModelRequest, ModelResponse, Provider, ToolCall
from datakeel.core.errors import ValidationError
from datakeel.core.harness_models import TokenUsage
from datakeel.runtime.tracing import tracing_disabled


def _message(message: ChatMessage) -> BaseMessage:
    if message.role == "assistant":
        return AIMessage(
            content=message.content,
            name=message.name,
            tool_calls=[
                {"id": call.id, "name": call.name, "args": call.arguments.root, "type": "tool_call"}
                for call in message.tool_calls
            ],
        )
    if message.role == "tool":
        return ToolMessage(
            content=message.content, tool_call_id=message.tool_call_id or "", name=message.name
        )
    kind = SystemMessage if message.role == "system" else HumanMessage
    return kind(content=message.content, name=message.name)


def _response(message: AIMessage) -> ModelResponse:
    if message.invalid_tool_calls:
        msg = "Provider returned invalid tool arguments"
        raise ValidationError(msg)
    usage = message.usage_metadata
    known = usage is not None and message.response_metadata.get("usage", {}) is not None
    details = (
        usage.get("input_token_details", InputTokenDetails()) if usage else InputTokenDetails()
    )
    return ModelResponse(
        content=message.text,
        tool_calls=[
            ToolCall.model_validate(
                {"id": call["id"], "name": call["name"], "arguments": call["args"]}
            )
            for call in message.tool_calls
        ],
        usage=TokenUsage.model_validate(
            {
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "cache_read_tokens": details.get("cache_read", 0),
                "cache_write_tokens": details.get("cache_creation", 0),
            },
            strict=True,
        )
        if known and usage
        else TokenUsage(),
        usage_known=known,
        stop_reason=message.response_metadata.get("finish_reason")
        or message.response_metadata.get("stop_reason")
        or "stop",
    )


class ScriptedChatModel(BaseChatModel):
    """Wrap the existing mutable fixture queue without changing its typed request."""

    _provider: Provider = PrivateAttr()

    def __init__(self, provider: Provider) -> None:
        """Retain the original fake or demo provider for deterministic accounting."""
        super().__init__(cache=False)
        self._provider = provider

    @property
    def _llm_type(self) -> str:
        return "datakeel-scripted"

    def bind_tools(
        self, tools: Sequence[object], *, tool_choice: str | None = None, **kwargs: object
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Bind tool declarations locally; no vendor tool binder is involved."""
        return self.bind(tools=list(tools), tool_choice=tool_choice, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        del messages, stop, kwargs
        if run_manager is None or "datakeel_request" not in run_manager.metadata:
            msg = "Scripted model requires typed request metadata"
            raise ValidationError(msg)
        request = ModelRequest.model_validate(run_manager.metadata["datakeel_request"])
        result = self._provider.complete(request)
        message = AIMessage(
            content=result.content,
            tool_calls=[
                {"id": call.id, "name": call.name, "args": call.arguments.root, "type": "tool_call"}
                for call in result.tool_calls
            ],
            response_metadata={"finish_reason": result.stop_reason},
            usage_metadata=UsageMetadata(
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                total_tokens=result.usage.input_tokens + result.usage.output_tokens,
                input_token_details=InputTokenDetails(
                    cache_read=result.usage.cache_read_tokens,
                    cache_creation=result.usage.cache_write_tokens,
                ),
            )
            if result.usage_known
            else None,
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def _invoke(model: BaseChatModel, request: ModelRequest) -> ModelResponse:
    tools = [
        {"type": "function", "function": tool.model_dump(mode="json")} for tool in request.tools
    ]
    with tracing_disabled():
        runnable = model.bind_tools(tools) if tools else model
        message = runnable.invoke(
            [_message(item) for item in request.messages],
            config={"metadata": {"datakeel_request": request.model_dump(mode="json")}},
            model=request.model,
            max_tokens=request.max_output_tokens,
        )
    return _response(message)


class ChatProvider:
    """Expose a synchronous chat model through Datakeel's provider protocol."""

    def __init__(self, model: BaseChatModel) -> None:
        """Accept an already configured model with explicit transport ownership."""
        self.model = model

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Translate vendor failures without retrying or inventing successful usage."""
        try:
            return _invoke(self.model, request)
        except (OpenAIError, AnthropicError, ValueError, KeyError, TypeError, IndexError) as error:
            msg = "Model provider request failed or returned invalid data"
            raise ValidationError(msg) from error


def complete(provider: Provider, request: ModelRequest) -> ModelResponse:
    """Run every model attempt through a chat model while retaining fixture identity."""
    if isinstance(provider, ChatProvider):
        return provider.complete(request)
    return _invoke(ScriptedChatModel(provider), request)
