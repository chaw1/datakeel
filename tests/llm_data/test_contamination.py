# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Only user-owned generated evaluation text participates in contamination checking."""

from pathlib import Path

from datakeel.core.llm_data_models import TrainingConfig
from datakeel.llm_data import analyze_sources
from tests.llm_data.test_engine import source

_QUESTION = (
    "Describe how a fictional silver river transports mineral particles from a mountain "
    "through a narrow valley and explain the seasonal influence of rainfall on its flow."
)


def test_exact_and_lightly_edited_evaluation_questions_are_reported(tmp_path: Path) -> None:
    """A changed middle word still matches when the remaining exact run is shorter than 13."""
    evaluation = source(tmp_path, [{"question": _QUESTION}], name="evaluation.jsonl")
    rows = [
        {"instruction": _QUESTION, "output": "An independently generated completion."},
        {
            "instruction": _QUESTION.replace("silver", "golden").replace("seasonal", "annual"),
            "output": "Another completion.",
        },
        {
            "instruction": "请比较两种不同排序算法的时间和空间复杂度。",
            "output": "一种算法需要额外空间,另一种可以原地完成。",
        },
    ]
    report = analyze_sources((source(tmp_path, rows),), evaluations=(evaluation,))
    assert report.issue_counts["contamination"] == 2
    assert len(report.contamination_hits) == 2
    assert all(item.related_id == "evaluation.jsonl:1" for item in report.contamination_hits)
    assert all(item.field.startswith("data.jsonl:") for item in report.contamination_hits)


def test_short_lightly_edited_question_uses_conservative_fallback(tmp_path: Path) -> None:
    """Short registered questions can lack any contiguous 13-word overlap after one edit."""
    question = (
        "Explain how an imaginary copper tree stores rainwater inside its hollow branches "
        "during winter."
    )
    evaluation = source(tmp_path, [{"text": question}], name="evaluation.jsonl")
    row = {
        "instruction": question.replace("copper", "bronze"),
        "output": "The branches contain storage chambers.",
    }
    report = analyze_sources((source(tmp_path, [row]),), evaluations=(evaluation,))
    assert report.issue_counts.get("contamination", 0) == 1


def test_unregistered_and_clean_data_have_no_contamination_signal(tmp_path: Path) -> None:
    """Vague topical overlap never substitutes for a registered text match."""
    evaluation = source(tmp_path, [{"question": _QUESTION}], name="evaluation.jsonl")
    data = source(
        tmp_path,
        [
            {
                "instruction": "How does a library catalog classify books by subject?",
                "output": "It uses controlled subject headings and identifiers.",
            }
        ],
    )
    assert "contamination" not in analyze_sources((data,)).issue_counts
    assert "contamination" not in analyze_sources((data,), evaluations=(evaluation,)).issue_counts


def test_text_evaluations_chinese_and_custom_ngram(tmp_path: Path) -> None:
    """Plain-text lines and Chinese character n-grams share the registered reference identity."""
    question = "请分析这个虚构小镇在雨季如何利用山谷中的水流为农田提供灌溉。"
    evaluation = source(tmp_path, [question, "\n", "x" * 3000], name="evaluation.txt")
    data = source(tmp_path, [{"instruction": question, "output": "小镇可以修建蓄水设施和渠道。"}])
    report = analyze_sources(
        (data,),
        TrainingConfig(contamination_ngram=5, max_line_bytes=1024),
        evaluations=(evaluation,),
    )
    assert report.issue_counts["contamination"] == 1
    assert report.evaluation_sha256


def test_short_question_typo_can_match_without_four_word_gram_overlap(tmp_path: Path) -> None:
    """Character retrieval recalls a typo while full-string confirmation rejects unrelated text."""
    question = "Explain reversible chemical reactions."
    evaluation = source(tmp_path, [{"question": question}], name="evaluation.jsonl")
    data = source(
        tmp_path,
        [
            {
                "instruction": "Explain reversibel chemical reactions.",
                "output": "A fictional response.",
            },
            {"instruction": "Explain chemical storage safety.", "output": "A different answer."},
        ],
    )
    report = analyze_sources((data,), evaluations=(evaluation,))
    assert report.issue_counts["contamination"] == 1
    assert report.samples[0].decision == "drop"
    assert report.samples[1].decision == "keep"
