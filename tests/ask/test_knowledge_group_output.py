# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep scalar output nouns distinct from grouped catalog-object lists."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("kind", "question"),
    [
        ("metric", "库存量按地区分组\uff0c列出各类数量。"),
        ("metric", "库存量按地区分组\uff0c列出各项金额。"),
        ("metric", "库存量按地区分组\uff0c显示各组数值。"),
        ("knowledge", "库存量按地区统计\uff0c列出各类来源表。"),
        ("knowledge", "库存量按地区统计\uff0c列出各组负责人。"),
        ("knowledge", "库存量按地区统计\uff0c列出各类下游指标。"),
    ],
)
def test_grouped_outputs_preserve_scalar_nouns_and_catalog_lists(kind: str, question: str) -> None:
    """Only an explicit scalar output noun is retained as part of a value command."""
    answer = registered_question(question, "库存量")
    assert ("knowledge" if answer else "metric") == kind
