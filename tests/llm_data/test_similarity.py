# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent near-duplicate recall, clean negatives and preference-pair signals."""

import json
import random
import string
from pathlib import Path

from datakeel.core.llm_data_models import TrainingConfig
from datakeel.llm_data import analyze_sources
from datakeel.llm_data.similarity import fingerprint, normalize
from tests.llm_data.test_engine import source


def test_normalization_covers_case_punctuation_and_unicode_width() -> None:
    """Width/case/space edits produce the same exact key in either language."""
    assert normalize("Hello, World!") == normalize("\uff28\uff25\uff2c\uff2c\uff2f world")
    assert normalize("你好, 世界\uff01") == normalize("你 好世界")
    assert fingerprint("distinct text") == fingerprint("distinct text")


def test_near_duplicates_find_light_edits_without_pairwise_scans(tmp_path: Path) -> None:
    """A planted series of substitutions is retrieved through independent MinHash bands."""
    rng = random.Random(2928)  # noqa: S311  # Reproducible generated test corpus.
    originals = [
        " ".join("".join(rng.choices(string.ascii_lowercase, k=8)) for _ in range(18))
        for _ in range(100)
    ]
    rows = [
        {"instruction": text, "output": "A detailed explanation of this generated topic."}
        for text in originals
    ]
    for text in originals:
        modified = text[:50] + ("z" if text[50] != "z" else "q") + text[51:]
        rows.append(
            {"instruction": modified, "output": "A detailed explanation of this generated topic."}
        )
    report = analyze_sources((source(tmp_path, rows),), TrainingConfig(sample_limit=200))
    hits = report.issue_counts.get("near_duplicate", 0) + report.issue_counts.get(
        "exact_duplicate", 0
    )
    assert hits >= 95
    assert report.files[0].records == 200


def test_distinct_answers_to_long_identical_prompts_are_conflicts_not_duplicates(
    tmp_path: Path,
) -> None:
    """Shared prompt boilerplate cannot erase a materially different completion."""
    prompt = "Please answer the following generated request with all necessary details. " * 8
    rows = [
        {"instruction": prompt, "output": "The answer is the red planet Mars."},
        {
            "instruction": prompt,
            "output": "This request describes a blue whale in the Pacific Ocean.",
        },
    ]
    report = analyze_sources((source(tmp_path, rows),))
    assert report.issue_counts["prompt_conflict"] == 1
    assert report.dropped == 0
    assert "near_duplicate" not in report.issue_counts


def test_clean_random_records_do_not_become_near_duplicates(tmp_path: Path) -> None:
    """Generated negative controls share no meaningful response or prompt content."""
    rng = random.Random(487)  # noqa: S311  # Reproducible generated negative controls.
    rows = [
        {
            "instruction": " ".join(
                "".join(rng.choices(string.ascii_lowercase, k=8)) for _ in range(12)
            ),
            "output": " ".join(
                "".join(rng.choices(string.ascii_lowercase, k=8)) for _ in range(12)
            ),
        }
        for _ in range(200)
    ]
    report = analyze_sources((source(tmp_path, rows),))
    assert "near_duplicate" not in report.issue_counts
    assert "exact_duplicate" not in report.issue_counts


def test_preference_identical_and_near_identical_are_always_reported(tmp_path: Path) -> None:
    """Chosen/rejected identity is checked even when records have unrelated prompts."""
    rows = [
        {
            "prompt": "Explain the first concept",
            "chosen": "The same response.",
            "rejected": "The same response.",
        },
        {
            "prompt": "Explain the second concept",
            "chosen": "This is a long detailed answer about a generated example.",
            "rejected": "This is a long detailed answer about the generated example.",
        },
        {"prompt": "Explain the third concept", "chosen": "", "rejected": "A rejected response."},
    ]
    report = analyze_sources((source(tmp_path, rows),))
    assert report.issue_counts.get("preference_identical", 0) == 1
    assert report.issue_counts.get("preference_near_identical", 0) == 1
    assert report.issue_counts.get("chosen_empty", 0) == 1
    assert report.dropped == 3
    assert json.loads(report.model_dump_json())["preference_records"] == 3
