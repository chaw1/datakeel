# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""New knowledge goldens assert actual JSON fields independently of scripted prose."""

import socket

import pytest

from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case


@pytest.mark.parametrize(
    "identity",
    [
        "37-ask-knowledge-owner",
        "38-ask-knowledge-upstream",
        "39-ask-knowledge-clarification",
        "40-ask-knowledge-reviewed",
    ],
)
def test_knowledge_goldens_are_offline_and_assert_structured_tool_results(
    identity: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network and provider configuration remain unavailable during production replay."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Knowledge golden attempted network or credential access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    case = next(item for item in load_cases() if item.id == identity)
    assert not case.expect.answer_contains
    assert "const" in case.expect.tool_results[0].content_schema.model_dump_json()
    result = run_case(case, "fake")
    assert result.passed, result.failures
