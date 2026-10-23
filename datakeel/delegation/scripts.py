# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve deterministic script assertions without changing ordinary response accounting."""

from datakeel.core.agent_models import ModelRequest, ModelResponse, ScriptedResponse
from datakeel.core.canary import PREFIX
from datakeel.core.errors import ValidationError


def prepare_script(
    request: ModelRequest, response: ModelResponse, errors: list[str]
) -> ModelResponse:
    """Check consumer identity and expand sentinel placeholders only for golden scripts."""
    if not isinstance(response, ScriptedResponse):
        return response
    if response.agent is not None and response.agent != request.agent_name:
        msg = f"Script expected agent {response.agent}; consumed by {request.agent_name}"
        errors.append(msg)
        raise ValidationError(msg)
    raw = response.model_dump_json(exclude={"agent"})
    canary = next(
        (part.text.rsplit(" ", 1)[-1] for part in request.segments if part.name == "canary"), ""
    )
    if canary:
        raw = raw.replace("{{canary}}", canary)
        raw = raw.replace("{{canary_fragment}}", canary.removeprefix(PREFIX)[:16])
    return ModelResponse.model_validate_json(raw).model_copy(
        update={"usage_known": response.usage_known}
    )
