# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixture reviews are strict frozen data rather than special cases in evaluation code."""

import pytest
from pydantic import ValidationError

from datakeel.core.knowledge_reviews import KnowledgeReviews
from datakeel.harness.resources import contract_path
from datakeel.kg.loader import load_contract


def test_review_contract_loads_explicit_relation_and_link_decisions() -> None:
    """Both association choices and both relationship decisions survive typed contract loading."""
    reviews = load_contract(contract_path("ask/enterprise-reviews.yaml"), KnowledgeReviews)
    assert len(reviews.relations) == 2
    assert len(reviews.links) == 2
    assert {item.status for item in reviews.relations} == {"accepted", "rejected"}
    assert {item.status for item in reviews.links} == {"accepted", "rejected"}
    with pytest.raises(ValidationError, match="Extra inputs"):
        KnowledgeReviews.model_validate({"decisions": []})
