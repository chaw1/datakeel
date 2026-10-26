# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed response fields shared by compatible visual transcription protocols."""

from pydantic import BaseModel, ConfigDict, Field


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


class TranscriptionResponse(_WireModel):
    """Consume a frozen OpenAI-compatible or native Ollama response without vendor extras."""

    choices: tuple[_Choice, ...] = ()
    message: _Message = Field(default_factory=_Message)
    usage: _Usage = Field(default_factory=_Usage)
    done_reason: str | None = None
    prompt_eval_count: int | None = Field(default=None, ge=0)
    eval_count: int | None = Field(default=None, ge=0)
