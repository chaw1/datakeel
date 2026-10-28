# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Sensor-gap questions rank saved intervals without reading source files or calling models."""

from pathlib import Path

import pytest

from datakeel.ask.profile import parse_profile_question
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.storage.ask_store import get_answer, store_answer
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.dataset_service import resolve_download
from datakeel.storage.events import all_events
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.profile_queries import read_profiles
from tests.ask.profile_helpers import SENSOR_QUESTION, publish_sensors


def test_profile_answer_when_published_ranks_devices_with_exact_immutable_sources(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every count and duration is backed by saved UTC endpoints and original row numbers."""
    dataset = publish_sensors(db, tmp_path / "sources")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Profile questions must never read source files")

    with monkeypatch.context() as isolated:
        isolated.setattr(Path, "read_text", forbidden)
        isolated.setattr(Path, "read_bytes", forbidden)
        isolated.setattr("datakeel.operators.table.io.read_table", forbidden)
        isolated.setattr("datakeel.storage.datasets.materialize_files", forbidden)
        answer = ask_data(db, AskRequest(question=SENSOR_QUESTION))
    assert answer.status == "answered"
    assert answer.answer_kind == "profile"
    assert answer.profile is not None
    assert answer.profile.dataset == dataset
    assert answer.profile.scope == "sampling_time_axis"
    assert answer.profile.sort_by == "total_gap_ms"
    ranks = answer.profile.ranking
    assert [(rank.device, rank.interval_count, rank.total_gap_ms) for rank in ranks] == [
        ("beta", 2, 4000),
        ("alpha", 1, 3000),
    ]
    assert "温度独有" in answer.message
    assert all(item.rows and item.file_id for rank in ranks for item in rank.evidence)
    assert all(item.source_file_id != item.file_id for rank in ranks for item in rank.evidence)
    assert ranks[1].evidence[0].rows == (4, 2)
    assert ranks[1].evidence[0].row_coordinates == "original_source"
    with db.session() as session:
        event = next(
            event for event in all_events(session) if event.idempotency_key == f"ask:{answer.id}"
        )
    assert {"dataset", "version", "file"} <= {item.asset_type for item in event.inputs}
    assert get_answer(db, answer.id) == answer
    assert "profile" in answer.model_dump(mode="json")
    assert answer.sql is None
    assert answer.result is None


@pytest.mark.parametrize(
    ("question", "sort_by"),
    [
        ("Which device has the most temperature gaps?", "gap_count"),
        ("Which sensor has the longest gaps?", "total_gap_ms"),
        ("哪台设备断档次数最多", "gap_count"),
        ("哪台设备的温度断档时长最长", "total_gap_ms"),
    ],
)
def test_profile_question_when_explicit_uses_declared_ranking_measure(
    db: Database,
    tmp_path: Path,
    question: str,
    sort_by: str,
) -> None:
    """Chinese and English count/duration questions state their measurement explicitly."""
    publish_sensors(db, tmp_path / "sources")
    answer = ask_data(db, AskRequest(question=question))
    assert answer.status == "answered"
    assert answer.profile is not None
    assert answer.profile.sort_by == sort_by


@pytest.mark.parametrize(
    "question",
    [
        "上个季度华东区零售额是多少",
        "Who owns temperature?",
        "Which device table has an owner?",
        "How many sensor records are there?",
        "temperature列空值率是多少",
        "Which metric has most users?",
    ],
)
def test_profile_parser_when_other_intents_does_not_capture_existing_questions(
    question: str,
) -> None:
    """Explicit gap rankings cannot replace ordinary metric or knowledge parsing."""
    assert parse_profile_question(AskRequest(question=question)) is None


def test_profile_parser_when_metric_or_knowledge_is_pinned_preserves_explicit_intent() -> None:
    """Caller-selected metric and knowledge semantics remain authoritative."""
    assert (
        parse_profile_question(AskRequest(question=SENSOR_QUESTION, metric_id="gap_metric")) is None
    )
    assert (
        parse_profile_question(AskRequest(question=SENSOR_QUESTION, knowledge_intent="owner"))
        is None
    )


def test_profile_answer_when_datasets_ambiguous_requires_a_dataset_choice(
    db: Database,
    tmp_path: Path,
) -> None:
    """Device labels from unrelated datasets never join into one ranking."""
    first = publish_sensors(db, tmp_path / "first", "First sensors")
    publish_sensors(db, tmp_path / "second", "Second sensors")
    answer = ask_data(db, AskRequest(question=SENSOR_QUESTION))
    assert answer.status == "clarification"
    assert answer.profile is not None
    assert answer.profile.ranking == ()
    assert len(answer.profile.candidates) == 2
    resolved = ask_data(db, AskRequest(question=SENSOR_QUESTION, subject_id=first.dataset_id))
    assert resolved.status == "answered"
    assert resolved.profile is not None
    assert resolved.profile.dataset == first
    unknown = ask_data(db, AskRequest(question=SENSOR_QUESTION, subject_id="missing"))
    assert unknown.status == "unanswerable"
    assert unknown.profile is not None
    assert unknown.profile.reason_code == "unknown_subject"


def test_profile_answer_when_current_manifest_has_no_measurements_does_not_reuse_history(
    db: Database,
    tmp_path: Path,
) -> None:
    """A newly published unprofiled version cannot inherit facts from an older manifest."""
    dataset = publish_sensors(db, tmp_path / "sources")
    answered = ask_data(db, AskRequest(question=SENSOR_QUESTION))
    with db.session() as session:
        original = session.get(DatasetRow, dataset.dataset_id)
        assert original is not None
        session.add(VersionRow(dataset_id=dataset.dataset_id, manifest=original.files))
        session.commit()
    refused = ask_data(db, AskRequest(question=SENSOR_QUESTION))
    assert refused.status == "unanswerable"
    assert refused.profile is not None
    assert refused.profile.reason_code == "no_profile"
    assert get_answer(db, answered.id) == answered


@pytest.mark.parametrize(
    ("remove", "reason"),
    [
        ("gaps", "incomplete_profile"),
        ("columns", "unknown_column"),
        ("intervals", "no_recorded_gaps"),
        ("invalid", "incomplete_profile"),
    ],
)
def test_profile_answer_when_saved_measurements_are_incomplete_refuses_without_values(
    db: Database,
    tmp_path: Path,
    remove: str,
    reason: str,
) -> None:
    """Missing, malformed or absent interval evidence never yields a guessed device rank."""
    dataset = publish_sensors(db, tmp_path / "sources")
    with db.session() as session:
        latest = session.get(VersionRow, dataset.version_id)
        assert latest is not None
        manifest = latest.manifest
        metadata = manifest[0]["metadata"]
        if remove == "gaps":
            metadata["timeseries"] = {}
        elif remove == "columns":
            metadata.pop("table_profile")
        elif remove == "intervals":
            metadata["timeseries"]["gaps"]["intervals"] = []
            metadata["timeseries"]["gaps"]["total_gap_ms"] = 0
        else:
            metadata["timeseries"]["gaps"] = {"invalid": True}
        session.add(VersionRow(dataset_id=dataset.dataset_id, manifest=manifest))
        session.commit()
    answer = ask_data(db, AskRequest(question=SENSOR_QUESTION))
    assert answer.status == "unanswerable"
    assert answer.profile is not None
    assert answer.profile.ranking == ()
    assert answer.profile.reason_code == reason


def test_profile_reads_when_file_is_deleted_hides_current_metadata(
    db: Database,
    tmp_path: Path,
) -> None:
    """Logical deletion applies to profile reads as it does to normal file reads."""
    dataset = publish_sensors(db, tmp_path / "sources")
    source = read_profiles(db)[0]
    with db.session() as session:
        session.add(
            FileStateRow(dataset_id=dataset.dataset_id, file_id=source.file_id, deleted=True)
        )
        session.commit()
    assert read_profiles(db) == ()


def test_profile_answer_when_original_source_is_deleted_refuses_without_hiding_live_sources(
    db: Database,
    tmp_path: Path,
) -> None:
    """A visible derived profile cannot cite a logically deleted original file/version."""
    removed = publish_sensors(db, tmp_path / "removed")
    retained = publish_sensors(db, tmp_path / "retained", "Retained sensors")
    sources = {item.dataset.dataset_id: item for item in read_profiles(db)}
    origin = sources[removed.dataset_id].gaps[0]
    live_origin = sources[retained.dataset_id].gaps[0]
    assert resolve_download(
        db, removed.dataset_id, origin.source_file_id, origin.source_version_id
    ).path.is_file()
    with db.session() as session:
        session.add(
            FileStateRow(dataset_id=removed.dataset_id, file_id=origin.source_file_id, deleted=True)
        )
        session.commit()
    with pytest.raises(NotFoundError, match="File not found"):
        resolve_download(db, removed.dataset_id, origin.source_file_id, origin.source_version_id)
    current = {item.dataset.dataset_id: item for item in read_profiles(db)}
    assert current[removed.dataset_id].file_id == sources[removed.dataset_id].file_id
    assert not current[removed.dataset_id].valid
    refused = ask_data(db, AskRequest(question=SENSOR_QUESTION, subject_id=removed.dataset_id))
    assert refused.status == "unanswerable"
    assert refused.profile is not None
    assert refused.profile.reason_code == "incomplete_profile"
    assert refused.profile.ranking == ()
    live = ask_data(db, AskRequest(question=SENSOR_QUESTION, subject_id=retained.dataset_id))
    assert live.status == "answered"
    assert live.profile is not None
    assert live.profile.ranking
    assert resolve_download(
        db, retained.dataset_id, live_origin.source_file_id, live_origin.source_version_id
    ).path.is_file()


def test_profile_reads_when_dataset_has_no_version_returns_no_measurement(db: Database) -> None:
    """An incomplete storage row supplies no inferred profile facts."""
    with db.session() as session:
        session.add(DatasetRow(name="Unpublished"))
        session.commit()
    assert read_profiles(db) == ()


def test_profile_store_when_dataset_pin_differs_rejects_forged_answer(
    db: Database,
    tmp_path: Path,
) -> None:
    """Persistence binds the explicit selected dataset to the answer's actual evidence."""
    publish_sensors(db, tmp_path / "sources")
    answer = ask_data(db, AskRequest(question=SENSOR_QUESTION))
    with pytest.raises(ValidationError, match="explicitly selected dataset"):
        store_answer(
            db,
            AskRequest(
                question=SENSOR_QUESTION,
                subject_id="other",
                reference_instant=answer.reference_instant,
            ),
            answer,
        )


def test_profile_schema_when_old_metric_refuses_keeps_optional_field_omitted(db: Database) -> None:
    """Default profile absence preserves existing tool payloads and exact golden schemas."""
    answer = ask_data(db, AskRequest(question="上个季度华东区零售额是多少"))
    assert "profile" not in answer.model_dump(mode="json")
    assert AskAnswer.model_validate(answer.model_dump()) == answer


@pytest.mark.parametrize("column", ["Temperature", "温度"])
def test_profile_question_when_temperature_header_uses_explicit_aliases(
    db: Database,
    tmp_path: Path,
    column: str,
) -> None:
    """Registered English case variants and the exact Chinese alias remain usable."""
    publish_sensors(db, tmp_path / "sources", column=column)
    assert ask_data(db, AskRequest(question=SENSOR_QUESTION)).status == "answered"


@pytest.mark.parametrize("origin", [None, "unregistered-file"])
def test_profile_question_when_original_source_cannot_be_verified_refuses(
    db: Database,
    tmp_path: Path,
    origin: str | None,
) -> None:
    """Source-row mappings cannot be attached to a guessed original file or version."""
    dataset = publish_sensors(db, tmp_path / "sources")
    with db.session() as session:
        version = session.get(VersionRow, dataset.version_id)
        assert version is not None
        manifest = version.manifest
        metadata = manifest[0]["metadata"]
        if origin is None:
            metadata.pop("original_source_file_id")
        else:
            metadata["original_source_file_id"] = origin
        session.add(VersionRow(dataset_id=dataset.dataset_id, manifest=manifest))
        session.commit()
    answer = ask_data(db, AskRequest(question=SENSOR_QUESTION))
    assert answer.status == "unanswerable"
    assert answer.profile is not None
    assert answer.profile.reason_code == "incomplete_profile"


def test_profile_question_when_duplicate_intervals_are_stored_refuses_inflated_counts(
    db: Database,
    tmp_path: Path,
) -> None:
    """Corrupt duplicate measurements produce a safe refusal, not a repeated count or crash."""
    dataset = publish_sensors(db, tmp_path / "sources")
    with db.session() as session:
        version = session.get(VersionRow, dataset.version_id)
        assert version is not None
        manifest = version.manifest
        intervals = manifest[0]["metadata"]["timeseries"]["gaps"]["intervals"]
        intervals.append(intervals[0])
        session.add(VersionRow(dataset_id=dataset.dataset_id, manifest=manifest))
        session.commit()
    answer = ask_data(db, AskRequest(question=SENSOR_QUESTION))
    assert answer.status == "unanswerable"
    assert answer.profile is not None
    assert answer.profile.ranking == ()
