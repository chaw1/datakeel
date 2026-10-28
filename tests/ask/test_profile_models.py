# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Profile answer boundaries reject unsupported numeric claims and incomplete evidence."""

import pytest
from pydantic import ValidationError

from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.profile_models import (
    DeviceGapRank,
    ProfileAnswer,
    ProfileDataset,
    ProfileGapEvidence,
)


def _answer() -> AskAnswer:
    request = AskRequest(question="Which device has most gaps?")
    evidence = ProfileGapEvidence(
        dataset_id="dataset",
        version_id="published",
        file_id="derived",
        filename="readings.csv",
        source_file_id="original",
        source_version_id="import",
        device="sensor-a",
        time_column="timestamp",
        start_ms=1000,
        end_ms=5000,
        gap_ms=3000,
        expected_interval_ms=1000,
        rows=(7, 3),
    )
    return AskAnswer(
        session_id="session",
        question=request.question,
        status="answered",
        message="Recorded sampling-axis intervals",
        reference_instant=request.reference_instant,
        answer_kind="profile",
        profile=ProfileAnswer(
            dataset=ProfileDataset(
                dataset_id="dataset", dataset_name="Generated", version_id="published"
            ),
            ranking=(
                DeviceGapRank(
                    device="sensor-a", interval_count=1, total_gap_ms=3000, evidence=(evidence,)
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("file_id", ""),
        ("source_file_id", ""),
        ("source_version_id", ""),
        ("rows", [0, 3]),
        ("rows", [3, 3]),
        ("rows", []),
        ("gap_ms", 4000),
    ],
)
def test_profile_model_when_interval_has_no_exact_source_rejects(field: str, value: object) -> None:
    """A duration cannot appear without original rows, file identity and interval arithmetic."""
    payload = _answer().model_dump()
    payload["profile"]["ranking"][0]["evidence"][0][field] = value
    with pytest.raises(ValidationError):
        AskAnswer.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("device", "other"),
        ("interval_count", 2),
        ("total_gap_ms", 4000),
        ("evidence", []),
    ],
)
def test_profile_model_when_aggregates_disagree_with_evidence_rejects(
    field: str, value: object
) -> None:
    """Counts and durations are reproducible from the entire evidence list."""
    payload = _answer().model_dump()
    payload["profile"]["ranking"][0][field] = value
    with pytest.raises(ValidationError):
        AskAnswer.model_validate(payload)


def test_profile_model_when_interval_is_counted_twice_rejects() -> None:
    """Equal row intervals cannot inflate a device's counts or aggregate duration."""
    payload = _answer().model_dump()
    rank = payload["profile"]["ranking"][0]
    rank["evidence"] *= 2
    rank["interval_count"], rank["total_gap_ms"] = 2, 6000
    with pytest.raises(ValidationError, match="counted twice"):
        AskAnswer.model_validate(payload)


@pytest.mark.parametrize("field", ["dataset_id", "version_id"])
def test_profile_model_when_published_scope_differs_rejects(field: str) -> None:
    """Intervals from another dataset or version cannot support the selected source."""
    payload = _answer().model_dump()
    payload["profile"]["ranking"][0]["evidence"][0][field] = "other"
    with pytest.raises(ValidationError, match="published dataset version"):
        AskAnswer.model_validate(payload)


@pytest.mark.parametrize(
    ("status", "field", "value"),
    [
        ("answered", "profile", None),
        ("answered", "profile", {}),
        ("answered", "result", {"columns": ["value"], "rows": [[1]]}),
        ("unanswerable", "status", "unanswerable"),
        ("clarification", "status", "clarification"),
        ("answered", "question", "e\u0301"),
    ],
)
def test_profile_model_when_state_is_inconsistent_rejects(
    status: str,
    field: str,
    value: object,
) -> None:
    """Safe refusal states contain no rankings and answered states contain only profile facts."""
    payload = _answer().model_dump()
    payload["status"], payload[field] = status, value
    with pytest.raises(ValidationError):
        AskAnswer.model_validate(payload)


def test_profile_model_when_clarification_has_no_choices_rejects() -> None:
    """A request for clarification must expose multiple concrete datasets."""
    payload = _answer().model_dump()
    payload["status"] = "clarification"
    payload["profile"].update(ranking=(), reason_code="ambiguous_dataset")
    with pytest.raises(ValidationError, match="multiple dataset candidates"):
        AskAnswer.model_validate(payload)


def test_profile_model_when_refusal_has_no_reason_rejects() -> None:
    """An empty numeric payload is not enough to explain refusal."""
    payload = _answer().model_dump()
    payload["status"] = "unanswerable"
    payload["profile"]["ranking"] = ()
    with pytest.raises(ValidationError, match="cannot assert numeric rankings"):
        AskAnswer.model_validate(payload)


def test_profile_model_when_kind_is_wrong_rejects_profile_payload() -> None:
    """New measurements cannot bypass legacy metric or knowledge validation."""
    payload = _answer().model_dump()
    payload["answer_kind"] = "metric"
    with pytest.raises(ValidationError, match="profile answer kind"):
        AskAnswer.model_validate(payload)


def test_profile_model_when_devices_repeat_rejects() -> None:
    """A profile cannot render two copies of the same device as separate ranked entries."""
    payload = _answer().model_dump()
    payload["profile"]["ranking"] *= 2
    with pytest.raises(ValidationError, match="distinct devices"):
        AskAnswer.model_validate(payload)
