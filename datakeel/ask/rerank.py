# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional candidate-ID reranking boundary, deliberately absent from the answer pipeline."""

from pydantic import ValidationError

from datakeel.core.agent_models import ChatMessage, ModelRequest, Provider
from datakeel.core.ask_models import CandidateOrder, RerankRequest


def rerank_candidates(provider: Provider, request: RerankRequest) -> CandidateOrder:
    """Accept only candidate-ID permutations and discard invented IDs or SQL responses."""
    original = tuple(dict.fromkeys(request.candidate_ids))
    if not original:
        return CandidateOrder(ordered_ids=())
    response = provider.complete(
        ModelRequest(
            model="fake-candidate-reranker",
            tools=[],
            segments=[],
            messages=[
                ChatMessage(
                    role="system",
                    content=(
                        'Return only JSON {"ordered_ids": [candidate ids]}. '
                        "Reorder supplied IDs only. Do not produce SQL or answer values."
                    ),
                ),
                ChatMessage(role="user", content=request.model_dump_json()),
            ],
        )
    )
    try:
        ranking = CandidateOrder.model_validate_json(response.content)
    except ValidationError:
        return CandidateOrder(ordered_ids=original)
    allowed = set(original)
    result = tuple(
        dict.fromkeys(identity for identity in ranking.ordered_ids if identity in allowed)
    )
    return CandidateOrder(
        ordered_ids=result + tuple(identity for identity in original if identity not in result)
    )
