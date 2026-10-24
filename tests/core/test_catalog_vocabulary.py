# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared vocabulary rules preserve complete identifiers and meaningful word fragments."""

import pytest

from datakeel.core.catalog_vocabulary import catalog_identifiers, normalized_subject_name


def test_shared_identifier_tokens_retain_qualified_segments_and_ignore_stop_words() -> None:
    """Both catalog linking and subject scanning consume these exact identifier boundaries."""
    assert catalog_identifiers("the 表 TABLES orders_clean source/main/orders main.orders") == (
        "orders_clean",
        "source/main/orders",
        "main.orders",
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("THE orders table", "orders"),
        ("the 表 tables", ""),
        ("  \uff2f\uff32\uff24\uff25\uff32\uff33   团队  ", "orders 团队"),
        ("thematic_table", "thematic_table"),
        ("出货额日报", "出货额日报"),
        ("the Morgan   Smith", "morgan smith"),
    ],
)
def test_whole_subject_normalization_removes_only_catalog_stop_words(
    text: str, expected: str
) -> None:
    """NFKC and whitespace folding do not truncate longer names containing known vocabulary."""
    assert normalized_subject_name(text) == expected
