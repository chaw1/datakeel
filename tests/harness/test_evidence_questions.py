# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The benchmark is a complete fixed contract with independent nonempty denominators."""

import hashlib
from collections import Counter
from pathlib import Path

import pytest
import yaml

from datakeel.harness.evidence_metrics import gold_subset
from datakeel.harness.evidence_questions import (
    EvidenceQuestion,
    EvidenceQuestionSuite,
    load_evidence_questions,
)
from datakeel.harness.resources import contract_path
from datakeel.sample_evidence import generate_samples


def test_question_contract_when_loaded_has_fifteen_questions_and_nonempty_gold(
    tmp_path: Path,
) -> None:
    """Every injection type has meaningful coverage in the actual thousand-sample generator."""
    suite, digest = load_evidence_questions()
    content = contract_path("evidence/questions.yaml").read_bytes()
    assert digest == hashlib.sha256(content).hexdigest()
    assert len(suite.questions) == 15
    assert min(Counter(question.target.kind for question in suite.questions).values()) >= 3
    gold = generate_samples(tmp_path / "samples")
    assert all(gold_subset(gold, question.target) for question in suite.questions)
    near = [gold_subset(gold, question.target) for question in suite.questions[:4]]
    assert near[2] < near[0]
    assert near[3] < near[1]
    changed = tmp_path / "questions.yaml"
    changed.write_bytes(content + b"\n# Digest tracks exact source bytes.\n")
    same, different_digest = load_evidence_questions(changed)
    assert same == suite
    assert digest != different_digest


@pytest.mark.parametrize("mutation", ["duplicate", "coverage", "count"])
def test_question_suite_when_structure_invalid_rejects(mutation: str) -> None:
    """Neither duplicated cases nor repeated categories may manufacture benchmark coverage."""
    suite, _ = load_evidence_questions()
    payload = suite.model_dump(mode="json")
    if mutation == "duplicate":
        payload["questions"][1]["id"] = payload["questions"][0]["id"]
    elif mutation == "coverage":
        for question in payload["questions"]:
            question["target"]["kind"] = "corrupt"
    else:
        payload["questions"].pop()
    with pytest.raises(ValueError, match=r"unique|three|15"):
        EvidenceQuestionSuite.model_validate(payload)


@pytest.mark.parametrize(
    "mutation", ["semantic_baseline", "semantic_property", "empty_evidence", "bound_query"]
)
def test_question_when_comparison_is_not_independent_rejects(mutation: str) -> None:
    """Reject semantic baselines and prebound identities before any evaluation starts."""
    suite, _ = load_evidence_questions()
    payload = suite.questions[0].model_dump(mode="json")
    if mutation == "semantic_baseline":
        payload["baseline"]["has_near_duplicate_in"] = "train"
    elif mutation == "semantic_property":
        payload["baseline"]["filters"] = [{"field": "metadata.caption_mentions", "value": []}]
    elif mutation == "empty_evidence":
        payload["with_evidence"].pop("has_near_duplicate_in")
    else:
        payload["baseline"]["dataset_id"] = "unrelated"
    with pytest.raises(ValueError, match=r"Baseline|Evidence queries|unbound"):
        EvidenceQuestion.model_validate(payload)


def test_question_contract_when_written_as_yaml_preserves_typed_object_sets(tmp_path: Path) -> None:
    """JSON-shaped contract serialization remains valid ObjectSet input for both query groups."""
    suite, _ = load_evidence_questions()
    path = tmp_path / "roundtrip.yaml"
    path.write_text(yaml.safe_dump(suite.model_dump(mode="json")), encoding="utf-8")
    assert load_evidence_questions(path)[0] == suite
