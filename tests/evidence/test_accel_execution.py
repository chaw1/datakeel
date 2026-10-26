# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Committed evidence facts retain backend attribution through cache reuse and replay."""

from collections.abc import Sequence
from pathlib import Path
from typing import Literal, NoReturn

import pytest
from sqlalchemy import select

from datakeel.core.errors import ExecutionError
from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_execution import EvidenceExecutionContext
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import FileItem
from datakeel.evidence.execution import EvidenceExecution
from datakeel.operators.evidence import near_duplicate_hashes
from datakeel.pipeline import run_pipeline
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence import generate_samples
from datakeel.storage.database import Database, EventRow
from datakeel.storage.datasets import materialize_files
from datakeel.storage.evidence_import import import_evidence_samples, source_manifest
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_runs import extraction_report
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute


@pytest.mark.parametrize("mode", ["prefix", "exact"])
def test_pipeline_three_settings_share_facts_and_report_current_backend_even_with_cache(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: Literal["prefix", "exact"]
) -> None:
    """Changing acceleration preserves assertion identities, full cache reuse and replay."""
    generate_samples(tmp_path / "samples", samples=20)
    dataset = import_evidence_samples(db, "generated acceleration samples", tmp_path / "samples")
    queue = DatabaseQueue(db)
    first = None
    for selection, implementation in (("off", "python"), ("auto", "rust"), ("required", "rust")):
        monkeypatch.setenv("DATAKEEL_ACCEL", selection)
        task = queue.submit(dataset.id, f"accel-{selection}", evidence_pipeline(mode=mode))
        lease = queue.claim()
        assert lease is not None
        assert execute(queue, lease)
        report = extraction_report(db, task)
        near = next(item for item in report.operators if item.operator == "evidence.near_duplicate")
        assert near.implementation == implementation
        assert near.implementation_version
        assert near.match_mode == mode
        if first is None:
            first = list_assertions(db)
            assert near.extracted == 20
        else:
            assert report.skipped_cached == report.inputs == 100
            assert list_assertions(db) == first
        with db.session() as session:
            event = session.scalar(
                select(EventRow).where(
                    EventRow.payload["source_ref"].as_string() == task,
                    EventRow.payload["operator"].as_string() == "evidence.near_duplicate",
                )
            )
            assert event is not None
            assert event.payload["quality"]["implementation"] == implementation
            assert event.payload["quality"]["implementation_version"]
            assert event.payload["quality"]["match_mode"] == mode
    assert rebuild_evidence(db).matches


def test_required_missing_extension_cannot_be_hidden_by_complete_cache(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A previously cached Python run cannot bypass the required native installation check."""
    generate_samples(tmp_path / "samples", samples=20)
    dataset = import_evidence_samples(db, "cached acceleration samples", tmp_path / "samples")
    queue = DatabaseQueue(db)
    monkeypatch.setenv("DATAKEEL_ACCEL", "off")
    queue.submit(dataset.id, "prime-cache", evidence_pipeline())
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    version, files = source_manifest(db, dataset.id)
    runtime = EvidenceExecution(
        db, EvidenceExecutionContext(task_id="required-cache", shard_id="new", version_id=version)
    )

    def missing() -> NoReturn:
        raise ModuleNotFoundError(name="datakeel_accel")

    monkeypatch.setattr(near_duplicate_hashes, "_load_accel", missing)
    monkeypatch.setenv("DATAKEEL_ACCEL", "required")
    with pytest.raises(ExecutionError, match="DATAKEEL_ACCEL=required"):
        run_pipeline(
            materialize_files(files),
            tmp_path / "required",
            evidence_pipeline(),
            operator_executor=runtime.execute_node,
        )


def _factual_files(files: list[FileItem]) -> list[FileItem]:
    return [
        file.model_copy(
            update={
                "metadata": {
                    key: value
                    for key, value in file.metadata.items()
                    if key
                    not in {
                        "near_duplicate_implementation",
                        "near_duplicate_implementation_version",
                    }
                }
            }
        )
        for file in files
    ]


def _facts(assertions: Sequence[Assertion]) -> list[str]:
    fields = set(ObservationDraft.model_fields)
    return sorted(
        ObservationDraft.model_validate(assertion.model_dump(include=fields)).model_dump_json()
        for assertion in assertions
    )


@pytest.mark.parametrize("mode", ["prefix", "exact"])
@pytest.mark.parametrize("selection", ["off", "auto", "required"])
def test_pipeline_cold_computation_matches_reference_output_and_committed_facts(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: Literal["prefix", "exact"],
    selection: str,
) -> None:
    """Each setting genuinely computes a fresh pipeline, with no persisted cache available."""
    generate_samples(tmp_path / "samples", samples=20)
    dataset = import_evidence_samples(db, "cold acceleration samples", tmp_path / "samples")
    version, files = source_manifest(db, dataset.id)
    context = EvidenceExecutionContext(task_id="unpublished", shard_id="cold", version_id=version)
    pipeline = evidence_pipeline(mode=mode)
    monkeypatch.setenv("DATAKEEL_ACCEL", "off")
    reference = EvidenceExecution(db, context)
    expected = run_pipeline(
        materialize_files(files),
        tmp_path / "reference",
        pipeline,
        operator_executor=reference.execute_node,
    )
    monkeypatch.setenv("DATAKEEL_ACCEL", selection)
    actual = EvidenceExecution(db, context)
    output = run_pipeline(
        materialize_files(files),
        tmp_path / "actual",
        pipeline,
        operator_executor=actual.execute_node,
    )
    assert _factual_files(output) == _factual_files(expected)
    expected_facts = _facts(
        [item for pending in reference.pending for item in pending.bundle.assertions]
    )
    assert (
        _facts([item for pending in actual.pending for item in pending.bundle.assertions])
        == expected_facts
    )
    assert not list_assertions(db)
    queue = DatabaseQueue(db)
    task = queue.submit(dataset.id, "cold-compute", pipeline)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    report = extraction_report(db, task)
    assert report.skipped_cached == 0
    near = next(item for item in report.operators if item.operator == "evidence.near_duplicate")
    assert near.implementation == ("python" if selection == "off" else "rust")
    assert near.implementation_version
    assert near.extracted == 20
    assert near.match_mode == mode
    assert _facts(list_assertions(db)) == expected_facts
