# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Send one metadata-free image through injected, retry-free HTTP transports."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from datakeel.core.transcription_auto import OCRReference
from datakeel.transcription.coordinates import decode_coordinates
from datakeel.transcription.prompt import transcription_prompt

if TYPE_CHECKING:
    from datakeel.core.transcription_models import (
        ImageInput,
        TranscriptionProfile,
        TranscriptionResult,
    )


class _WireModel(BaseModel):
    """Ignore unrelated provider metadata while keeping consumed response fields frozen."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class _Message(_WireModel):
    content: str = ""


class _Choice(_WireModel):
    message: _Message = Field(default_factory=_Message)
    finish_reason: str | None = None


class _Usage(_WireModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)


class _Response(_WireModel):
    choices: tuple[_Choice, ...] = ()
    message: _Message = Field(default_factory=_Message)
    usage: _Usage = Field(default_factory=_Usage)
    done_reason: str | None = None
    prompt_eval_count: int | None = Field(default=None, ge=0)
    eval_count: int | None = Field(default=None, ge=0)


def _body(profile: TranscriptionProfile, image: ImageInput) -> dict[str, JsonValue]:
    encoded = base64.b64encode(image.png).decode("ascii")
    prompt = transcription_prompt(profile.prompt_version, image.width, image.height)
    if profile.interface == "ollama":
        body: dict[str, JsonValue] = {
            "model": profile.model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
            "options": {
                "temperature": 0,
                "num_predict": profile.max_output_tokens,
                "num_ctx": profile.request_parameters.get("num_ctx", 16384),
            },
        }
        if "enable_thinking" in profile.request_parameters:
            body["think"] = profile.request_parameters["enable_thinking"]
        if profile.prompt_version == "image-transcription-v2":
            body["format"] = "json"
        return body
    return {
        "model": profile.model,
        "temperature": 0,
        "max_tokens": profile.max_output_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                ],
            }
        ],
        **(
            {"response_format": {"type": "json_object"}}
            if profile.prompt_version == "image-transcription-v2"
            else {}
        ),
        **profile.request_parameters,
    }


def _endpoint(profile: TranscriptionProfile) -> str:
    base = (profile.base_url or "").rstrip("/")
    if profile.interface == "ollama":
        return base + ("/chat" if base.endswith("/api") else "/api/chat")
    return base + "/chat/completions"


def _response(
    response: httpx.Response, profile: TranscriptionProfile, ocr: TranscriptionResult
) -> TranscriptionResult:
    if response.is_error:
        if "AllocationQuota.FreeTierOnly" in response.text or "insufficient_quota" in response.text:
            return ocr.model_copy(
                update={
                    "text": "",
                    "error": "服务商额度不足",
                    "quality_issues": ("provider_quota_exhausted",),
                }
            )
        return ocr.model_copy(update={"text": "", "error": f"http_{response.status_code}"})
    try:
        parsed = _Response.model_validate_json(response.content)
    except ValidationError:
        return ocr.model_copy(update={"text": "", "error": "invalid_response"})
    if profile.interface == "ollama":
        text, finish = parsed.message.content, parsed.done_reason
        input_tokens, output_tokens = parsed.prompt_eval_count, parsed.eval_count
    else:
        if not parsed.choices:
            return ocr.model_copy(update={"text": "", "error": "invalid_response"})
        text, finish = parsed.choices[0].message.content, parsed.choices[0].finish_reason
        input_tokens, output_tokens = parsed.usage.prompt_tokens, parsed.usage.completion_tokens
    located = (
        decode_coordinates(text, ocr.width, ocr.height)
        if profile.prompt_version == "image-transcription-v2"
        else None
    )
    return ocr.model_copy(
        update={
            "text": located.text if located else text,
            "lines": located.lines if located else ocr.lines,
            "finish_reason": finish or "stop",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
    )


def request_transcription(
    profile: TranscriptionProfile,
    image: ImageInput,
    ocr: TranscriptionResult,
    client: httpx.Client,
    api_key: str,
) -> TranscriptionResult:
    """Preserve safe failure categories without retries, redirects or provider body leakage."""
    result = ocr.model_copy(
        update={
            "backend": "vlm",
            "model": profile.model,
            "mode": "vlm",
            "input_tokens": None,
            "output_tokens": None,
            "error": None,
            "quality_issues": (),
            "ocr_reference": OCRReference(text=ocr.text, error=ocr.error)
            if profile.prompt_version == "image-transcription-v2"
            else ocr.ocr_reference,
        }
    )
    headers = {"accept": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    try:
        response = client.post(
            _endpoint(profile),
            json=_body(profile, image),
            headers=headers,
            timeout=profile.timeout_seconds,
            follow_redirects=False,
        )
    except httpx.TimeoutException:
        return result.model_copy(update={"text": "", "error": "timeout"})
    except httpx.RequestError:
        return result.model_copy(update={"text": "", "error": "provider_error"})
    return _response(response, profile, result)
