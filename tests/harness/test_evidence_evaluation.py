# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence goldens assess actual tool observations, extraction failures, and published versions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.harness_eval import ExpectedToolResult, ObservedToolResult
from datakeel.core.models import JsonDocument
from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case
from datakeel.harness.tool_assessment import selection_refs, tool_failures
from datakeel.storage import evidence_queries

if TYPE_CHECKING:
    from datakeel.actions.models import ActionRun
    from datakeel.core.harness_eval import GoldenCase
    from datakeel.core.models import AssetRef, FileItem
    from datakeel.evidence.query_models import EvidenceExplanation
    from datakeel.operators.evidence.common import EvidenceParams
    from datakeel.storage.database import Database


def _case(identifier: str) -> GoldenCase:
    return next(item for item in load_cases() if item.id == identifier)


def test_explanation_when_script_says_unknown_but_real_states_missing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A correct scripted sentence cannot conceal missing actual label-gap observations."""
    original = evidence_queries.explain_sample

    def missing_states(
        db: Database, asset_id: str, version_id: str | None = None
    ) -> EvidenceExplanation:
        return original(db, asset_id, version_id).model_copy(update={"states": []})

    monkeypatch.setattr(evidence_queries, "explain_sample", missing_states)
    result = run_case(_case("14-evidence-unknown"), "fake")
    assert not result.passed
    assert "unknown" in result.final_answer
    assert result.fixture_error is None
    assert any("Tool content mismatch: explain_sample" in failure for failure in result.failures)


def test_explanation_when_extraction_fails_returns_measured_case_without_claiming_tool_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator failure becomes case evidence, rather than an unparseable CLI crash."""

    def failed_gap(file: FileItem, params: EvidenceParams) -> FileItem:
        msg = "invalid absent observation from the generated fixture"
        raise ValueError(msg)

    monkeypatch.setattr("datakeel.operators.evidence.label_gap._gaps", failed_gap)
    result = run_case(_case("14-evidence-unknown"), "fake")
    assert not result.passed
    assert result.fixture_error is not None
    assert "invalid absent observation" in result.fixture_error
    assert result.stop_reasons == ["fixture_failure"]
    assert result.tool_sequence == []
    assert result.tool_results == []
    assert result.turns == result.tokens == 0


@pytest.mark.parametrize("missing", ["selection", "publication"])
def test_version_when_selection_or_publication_missing_fails_even_if_script_claims_success(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    """Creation requires an actual version manifest matching the measured query selection."""

    def missing_version(
        db: Database, dataset_id: str, runs: list[ActionRun]
    ) -> dict[str, list[str]]:
        return {}

    def missing_selection(observation: ObservedToolResult) -> list[AssetRef]:
        return []

    if missing == "publication":
        monkeypatch.setattr("datakeel.harness.execution._version_outputs", missing_version)
    else:
        monkeypatch.setattr("datakeel.harness.assessment.selection_refs", missing_selection)
    result = run_case(_case("15-evidence-version"), "fake")
    assert not result.passed
    assert "Created a version" in result.final_answer
    expected = (
        "Published version differs" if missing == "publication" else "Frozen selection differs"
    )
    assert any(expected in failure for failure in result.failures)


def test_tool_expectations_when_calls_status_refs_or_content_wrong_report_each_failure() -> None:
    """Tool evidence requirements remain independently falsifiable and missing data is explicit."""
    expected = ExpectedToolResult(
        name="query_evidence", calls=2, content_schema=JsonDocument({"required": ["data"]})
    )
    observed = ObservedToolResult(
        name="query_evidence", status="FAILED", content=JsonDocument({}), asset_refs=[]
    )
    failures = tool_failures([expected], [observed])
    assert len(failures) == 4
    assert selection_refs(observed) == []
