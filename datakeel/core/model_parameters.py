# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed thinking and context controls shared by every configured model request."""

from pydantic import JsonValue

REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high")


def request_parameter_valid(name: str, value: JsonValue) -> bool:
    """Permit only typed thinking and context controls, never transport overrides."""
    return (
        (name == "enable_thinking" and isinstance(value, bool))
        or (
            name == "num_ctx"
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value > 0
        )
        or (name == "reasoning_effort" and value in REASONING_EFFORTS)
    )
