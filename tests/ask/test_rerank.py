# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fake providers may reorder supplied identities but cannot introduce SQL or new metrics."""

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.ask.rerank import rerank_candidates
from datakeel.core.agent_models import ModelResponse
from datakeel.core.ask_models import RerankRequest


def test_rerank_filters_unknown_ids_duplicates_and_appends_omitted_candidates() -> None:
    """Only the supplied candidate set survives arbitrary provider output."""
    provider = FakeProvider([ModelResponse(content='{"ordered_ids":["b","absent","b"]}')])
    result = rerank_candidates(
        provider, RerankRequest(question="收入", candidate_ids=("a", "b", "c"))
    )
    assert result.ordered_ids == ("b", "a", "c")
    assert len(provider.requests) == 1
    assert provider.requests[0].tools == []


@pytest.mark.parametrize(
    "content",
    [
        "SELECT * FROM secret",
        '{"sql":"DELETE FROM orders","ordered_ids":["b","a"]}',
        '{"ordered_ids":[123]}',
        "invalid json",
    ],
)
def test_rerank_refuses_model_sql_or_malformed_contract(content: str) -> None:
    """Invalid model responses leave deterministic candidate ordering intact."""
    provider = FakeProvider([ModelResponse(content=content)])
    result = rerank_candidates(provider, RerankRequest(question="收入", candidate_ids=("a", "b")))
    assert result.ordered_ids == ("a", "b")


def test_rerank_empty_candidates_does_not_invoke_model() -> None:
    """No model path is available to invent a candidate for an unmatched question."""
    provider = FakeProvider([])
    assert (
        rerank_candidates(provider, RerankRequest(question="未知", candidate_ids=())).ordered_ids
        == ()
    )
    assert provider.requests == []
