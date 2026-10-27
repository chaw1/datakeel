# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Narrative punctuation must not split evidence strings or common name abbreviations."""

import pytest

from datakeel.datasheets.sentences import split_sentences


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("Dr. Elena Petrova is the owner. The dataset contains 12 files.", 2),
        ("Mr. Cedar owns the dataset. It contains 12 files.", 2),
        ("Collection date: Jan. 2 2026. The dataset contains 12 files.", 2),
        ('Entities: [{"name": "Dr. Elena Petrova", "type": "person"}].', 1),
        ('Entities: [{"name": "Cedar \\"Research\\" Unit", "type": "organization"}].', 1),
        ("Source text: \u2018Dr. Elena. Cedar Unit.\u2019 数据集包含12个文件。", 1),
        ("The dataset's owner is Cedar Unit. There are 12 files.", 2),
        ("The quality score is 98.3%. The dataset contains 12 files.", 2),
        ("数据集包含12个文件。负责人是星河团队。", 2),
        ("This is nested (source text. Kept together). A separate sentence.", 2),
    ],
)
def test_sentence_split_preserves_data_and_counts_assertions(text: str, count: int) -> None:
    """Only punctuation outside quoted or parenthesized data separates assertions."""
    result = split_sentences(text)
    assert len(result) == count
    assert " ".join(result).replace(" ", "") == text.replace(" ", "")
