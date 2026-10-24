# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Translate structured vendor responses into the domain extraction protocol."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from anthropic import AnthropicError
from anthropic import APIStatusError as AnthropicStatusError
from anthropic import APITimeoutError as AnthropicTimeoutError
from langchain_core.messages import AIMessage, HumanMessage
from openai import APIStatusError as OpenAIStatusError
from openai import APITimeoutError as OpenAITimeoutError
from openai import LengthFinishReasonError, OpenAIError

from datakeel.core.errors import ProviderError
from datakeel.core.kg_models import ExtractionResult, RawExtraction
from datakeel.extraction_runtime.transport import chat_model, tracing_disabled
from datakeel.kg.prompt import extraction_prompt, output_schema

if TYPE_CHECKING:
    from collections.abc import Generator

    import httpx
    from langchain_anthropic import ChatAnthropic
    from langchain_core.language_models import LanguageModelInput
    from langchain_core.runnables import Runnable
    from langchain_openai import ChatOpenAI
    from pydantic import JsonValue

    from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
    from datakeel.core.kg_models import TextBlock


def _parameters(profile: ExtractionProfile) -> dict[str, object]:
    parameters: dict[str, object] = {}
    extra: dict[str, JsonValue] = {}
    for key, value in profile.request_parameters.items():
        if key == "reasoning_effort" or (key == "thinking" and profile.provider == "anthropic"):
            parameters[key] = value
        else:
            extra[key] = value
    if extra:
        parameters["extra_body"] = extra
    return parameters


def _bind(
    model: ChatOpenAI | ChatAnthropic, profile: ExtractionProfile, schema: KGSchema
) -> Runnable[LanguageModelInput, AIMessage]:
    shape = output_schema(schema)
    parameters = _parameters(profile)
    if profile.output_method == "function_calling":
        tool = {"name": "KGExtraction", "description": "Extract entities and supported relations."}
        if profile.provider == "anthropic":
            return model.bind(
                tools=[{**tool, "input_schema": shape}],
                tool_choice={"type": "tool", "name": "KGExtraction"},
                **parameters,
            )
        return model.bind(
            tools=[{"type": "function", "function": {**tool, "parameters": shape}}],
            tool_choice={"type": "function", "function": {"name": "KGExtraction"}},
            parallel_tool_calls=False,
            **parameters,
        )
    if profile.output_method == "json_schema":
        if profile.provider == "anthropic":
            return model.bind(
                output_config={"format": {"type": "json_schema", "schema": shape}}, **parameters
            )
        return model.bind(
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "KGExtraction", "strict": True, "schema": shape},
            },
            **parameters,
        )
    if profile.provider != "anthropic":
        parameters["response_format"] = {"type": "json_object"}
    return model.bind(**parameters)


def _result(message: AIMessage, profile: ExtractionProfile) -> ExtractionResult:
    reason = str(
        message.response_metadata.get("finish_reason")
        or message.response_metadata.get("stop_reason")
        or "stop"
    )
    usage = message.usage_metadata
    known = usage is not None and message.response_metadata.get("usage", {}) is not None
    output = RawExtraction()
    if reason not in {"length", "max_tokens"}:
        if message.invalid_tool_calls:
            msg = "parse_error"
            raise ProviderError(msg)
        if profile.output_method == "function_calling":
            if len(message.tool_calls) != 1 or message.tool_calls[0]["name"] != "KGExtraction":
                msg = "parse_error"
                raise ProviderError(msg)
            output = RawExtraction.model_validate(message.tool_calls[0]["args"])
        else:
            output = RawExtraction.model_validate_json(message.text)
    return ExtractionResult(
        output=output,
        finish_reason=reason,
        input_tokens=usage["input_tokens"] if known and usage else None,
        output_tokens=usage["output_tokens"] if known and usage else None,
    )


class LLMExtractor:
    """Adapt a configured chat model without framework objects crossing the boundary."""

    def __init__(self, profile: ExtractionProfile, model: ChatOpenAI | ChatAnthropic) -> None:
        """Retain caller-owned transport configuration for this extraction run."""
        self.profile = profile
        self.model = model

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        """Make exactly one request and preserve truncation and unknown usage explicitly."""
        try:
            with tracing_disabled():
                model = _bind(self.model, self.profile, schema)
                message = model.invoke([HumanMessage(content=extraction_prompt(block, schema))])
            return _result(message, self.profile)
        except LengthFinishReasonError as error:
            usage = error.completion.usage
            return ExtractionResult(
                output=RawExtraction(),
                finish_reason="length",
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
            )
        except (OpenAITimeoutError, AnthropicTimeoutError) as error:
            msg = "timeout"
            raise ProviderError(msg) from error
        except (OpenAIStatusError, AnthropicStatusError) as error:
            reason = f"http_{error.status_code}"
            raise ProviderError(reason, status_code=error.status_code) from error
        except ProviderError:
            raise
        except (OpenAIError, AnthropicError) as error:
            msg = "provider_error"
            raise ProviderError(msg) from error
        except (ValueError, KeyError, TypeError, IndexError) as error:
            msg = "parse_error"
            raise ProviderError(msg) from error


@contextmanager
def llm_extractor(
    profile: ExtractionProfile, api_key: str, client: httpx.Client, timeout: float = 30
) -> Generator[LLMExtractor]:
    """Build a real-provider adapter using only explicitly injected credentials and HTTP."""
    with chat_model(profile, api_key, client, timeout) as model:
        yield LLMExtractor(profile, model)
