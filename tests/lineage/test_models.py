# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Lineage API models reject undeclared public fields."""

import pytest
from pydantic import ValidationError

from datakeel.lineage.models import GraphView


def test_graph_unknown_fields_are_rejected() -> None:
    """Verify graph unknown fields are rejected."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        GraphView.model_validate({"nodes": [], "edges": [], "events": [], "private": True})
