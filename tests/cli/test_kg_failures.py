# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Graph evaluation failures stay visible in JSON, terminal output and durable history."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
import yaml

from datakeel.cli.kg_evaluation import evaluate
from datakeel.kg.extractors import FakeExtractor
from datakeel.storage.kg_evaluations import get_evaluation

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from datakeel.core.kg_contracts import ExtractionProfile
    from datakeel.storage.database import Database


@pytest.mark.parametrize("json_output", [True, False])
def test_cli_and_history_expose_failed_case_offsets_and_reason(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    json_output: bool,
) -> None:
    """Both presentation forms expose the same block evidence returned by saved history."""
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        yaml.safe_dump(
            {
                "id": "failure-fixture",
                "cases": [
                    {
                        "id": "fixture-one",
                        "lang": "en",
                        "text": "Acme uses Widget.",
                        "entities": [],
                        "relations": [],
                    }
                ],
            }
        )
    )

    @contextmanager
    def injected(profile: ExtractionProfile) -> Generator[FakeExtractor]:
        yield FakeExtractor(("parse_failure",))

    monkeypatch.setattr("datakeel.extraction_runtime.factory.create_extractor", injected)
    report = evaluate(db, "fake", cases, json_output=json_output)
    output = capsys.readouterr().out
    expected = {"case_id": "fixture-one", "start": 0, "end": 17, "reason": "parse_failure"}
    assert [item.model_dump() for item in report.failures] == [expected]
    assert get_evaluation(db, report.id).failures == report.failures
    if json_output:
        assert json.loads(output)["failures"] == [expected]
    else:
        assert "Failed block: fixture-one [0, 17): parse_failure" in output
