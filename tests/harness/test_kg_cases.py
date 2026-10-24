# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluation suites validate references and replay lookup cannot confuse names with content."""

from pathlib import Path

import pytest
import yaml

from datakeel.core.errors import ValidationError
from datakeel.kg.loader import contracts_path, get_schema
from datakeel.kg_eval.loader import load_cases, load_recording, original_records


def test_builtin_cases_preserve_all_labels_and_examples() -> None:
    """Retain the independent 24-passage corpus and all optional and trap triples."""
    suite, digest = load_cases(get_schema())
    assert len(suite.cases) == 24
    assert sum(len(case.entities) for case in suite.cases) == 161
    assert sum(len(case.relations) for case in suite.cases) == 114
    assert sum(len(case.optional) for case in suite.cases) == 25
    assert sum(len(case.traps) for case in suite.cases) == 12
    assert len(digest) == 64
    assert len(get_schema().examples) == 2


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("entities", [{"name": "x", "type": "undefined"}], "unknown entity type"),
        ("entities", [{"name": "x", "type": "person"}] * 2, "duplicate canonical entity"),
        ("relations", [{"head": "x", "relation": "unknown", "tail": "y"}], "unknown relation"),
        ("relations", [{"head": "x", "relation": "owns", "tail": "unknown"}], "undeclared gold"),
        ("relations", [{"head": "y", "relation": "owns", "tail": "x"}], "domain/range"),
    ],
)
def test_external_cases_reject_invalid_references(
    tmp_path: Path, field: str, replacement: list[dict[str, str]], message: str
) -> None:
    """Catch unknown schema references before executing an extractor."""
    case: dict[str, object] = {
        "id": "custom",
        "lang": "en",
        "text": "x owns y.",
        "entities": [{"name": "x", "type": "person"}, {"name": "y", "type": "dataset"}],
        "relations": [{"head": "x", "relation": "owns", "tail": "y"}],
    }
    case[field] = replacement
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump({"id": "custom", "cases": [case]}))
    with pytest.raises(ValidationError, match=message):
        load_cases(get_schema(), path)


def test_duplicate_case_identity_rejected(tmp_path: Path) -> None:
    """Prevent accidental overwrite of a benchmark denominator."""
    suite, _ = load_cases(get_schema())
    path = tmp_path / "cases.yaml"
    data = suite.model_dump(mode="json")
    data["cases"] = [data["cases"][0], data["cases"][0]]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValidationError, match="duplicate case identity"):
        load_cases(get_schema(), path)


def test_recordings_are_matched_by_content_and_preserve_original_predictions() -> None:
    """Changing a case ID is safe; reusing its ID for changed source text cannot reuse output."""
    suite, _ = load_cases(get_schema())
    archive = load_recording(contracts_path() / "recordings/qwen3.5.yaml")
    first = suite.cases[0]
    changed = suite.model_copy(
        update={
            "cases": (
                first.model_copy(update={"id": "renamed"}),
                first.model_copy(update={"text": "A completely different passage."}),
            )
        }
    )
    records = original_records(archive, changed)
    assert records[0].pid == "renamed"
    assert records[0].relations
    assert records[1].error == "replay_not_found"
    assert archive.records[-1].finish_reason == "length"
