# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tool caller and control parameters reject undeclared capabilities."""

import pytest
from pydantic import ValidationError

from datakeel.ontology.tool_models import ApproveToolParams, ExecuteToolParams, ToolCallContext


def test_tool_context_when_actor_spoofed_rejects_nonlocal_identity() -> None:
    """Expose only the single declared local identity to tool adapters."""
    with pytest.raises(ValidationError):
        ToolCallContext.model_validate({"actor": "administrator", "scopes": ["*"]})


def test_control_parameters_when_digest_missing_reject_unbound_decision() -> None:
    """Require explicit digest binding for both approval and execution tools."""
    for model in (ApproveToolParams, ExecuteToolParams):
        with pytest.raises(ValidationError):
            model.model_validate({"plan_id": "generated-plan"})
