# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The built-in training operator shares the same offline engine and typed configuration."""

import json
from pathlib import Path

import pytest

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY


def _file(tmp_path: Path, filename: str, text: str) -> FileItem:
    path = tmp_path / filename
    path.write_text(text)
    return FileItem(path=str(path), filename=filename, modality="text")


def test_training_operator_checks_jsonl_but_preserves_ordinary_text(tmp_path: Path) -> None:
    """Ordinary documents retain their established text-quality operator path."""
    row = json.dumps({"instruction": "Explain a generated subject", "output": "A detailed answer."})
    training = _file(tmp_path, "records.jsonl", row + "\n{broken\n")
    ordinary = _file(tmp_path, "notes.txt", "A short generated document.")
    result = REGISTRY["text.training_quality"].run([training, ordinary], tmp_path / "output")
    assert result.files[0].metadata["training_quality"]["records"] == 2
    assert result.files[0].metadata["training_quality"]["issue_counts"]["format_error"] == 1
    assert "training_quality" not in result.files[1].metadata
    assert result.files[0].id == training.id


def test_training_operator_freezes_configured_limits(tmp_path: Path) -> None:
    """Pipeline parameters must affect real observations and remain in the report."""
    training = _file(
        tmp_path, "records.ndjson", '{"instruction":"Question","output":"A long answer"}\n'
    )
    report = REGISTRY["text.training_quality"].run(
        [training], tmp_path / "output", {"max_tokens": 1}
    )
    measured = report.files[0].metadata["training_quality"]
    assert measured["config"]["max_tokens"] == 1
    assert measured["issue_counts"]["token_limit"] == 1
    with pytest.raises(ValueError, match="Extra inputs"):
        REGISTRY["text.training_quality"].run([], tmp_path / "output", {"undeclared": True})


def test_training_operator_accepts_json_word_list_parameters(tmp_path: Path) -> None:
    """Configurable vocabularies survive the same JSON representation used by pipeline APIs."""
    training = _file(
        tmp_path, "records.jsonl", '{"instruction":"Question","output":"Custom screening phrase"}\n'
    )
    result = REGISTRY["text.training_quality"].run(
        [training], tmp_path / "output", {"refusal_phrases": ["screening phrase"]}
    )
    report = result.files[0].metadata["training_quality"]
    assert report["issue_counts"]["template_response"] == 1
    assert "safety_rule" not in report["issue_counts"]


def test_training_operator_rejects_removed_safety_configuration(tmp_path: Path) -> None:
    """Removed screening parameters cannot silently remain in a frozen pipeline plan."""
    with pytest.raises(ValueError, match="Extra inputs"):
        REGISTRY["text.training_quality"].run(
            [], tmp_path / "output", {"safety_terms": ["screening phrase"]}
        )
