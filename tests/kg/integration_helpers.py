# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated text datasets and injected adapters for the real action/worker boundary."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from datakeel.actions.models import ActionPlan, ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_execution import KGRun
from datakeel.core.kg_models import ExtractionResult, RawExtraction
from datakeel.core.models import BoundaryModel, FileItem, JsonDocument
from datakeel.kg.extractors import FakeExtractor
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.kg_store import list_runs
from datakeel.worker.runner import run_worker


class TextDataset(BoundaryModel):
    """Keep generated input identities available to selection and source-anchor assertions."""

    dataset_id: str
    version_id: str
    files: tuple[FileItem, ...]


def text_dataset(db: Database, directory: Path, texts: tuple[str, ...]) -> TextDataset:
    """Import distinct generated files through the ordinary immutable dataset path."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, text in enumerate(texts):
        path = directory / f"source-{index}.txt"
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    dataset = import_paths(db, "Generated graph integration", paths)
    version, files = source_manifest(db, dataset.id)
    return TextDataset(dataset_id=dataset.id, version_id=version, files=tuple(files))


def prepare_graph(
    db: Database, dataset: TextDataset, profile_id: str = "fake", file_ids: tuple[str, ...] = ()
) -> ActionPlan:
    """Freeze an ordinary local extraction request using its real manifest."""
    return prepare_action(
        db,
        "run_kg_extraction",
        JsonDocument(
            root={
                "dataset_id": dataset.dataset_id,
                "version_id": dataset.version_id,
                "profile_id": profile_id,
                "file_ids": list(file_ids),
            }
        ),
    )


def execute_graph(db: Database, plan: ActionPlan) -> KGRun:
    """Run one prepared action and return its actual terminal graph report."""
    action = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run_worker(db, once=True)
    return next(run for run in list_runs(db) if run.task_id == action.task_id)


def pair_result(head: str = "Acme", tail: str = "Widget") -> ExtractionResult:
    """Produce only explicit fixture observations, without extracting expected gold labels."""
    return ExtractionResult(
        output=RawExtraction(
            entities=(
                ExtractedEntity(name=head, type="organization"),
                ExtractedEntity(name=tail, type="system"),
            ),
            relations=(
                ExtractedRelation(
                    head=head, relation="uses", tail=tail, evidence=f"{head} uses {tail}."
                ),
            ),
        ),
        input_tokens=0,
        output_tokens=0,
    )


def install_adapter(
    monkeypatch: pytest.MonkeyPatch, results: tuple[ExtractionResult | str, ...]
) -> FakeExtractor:
    """Replace the provider construction boundary while leaving worker metering intact."""
    adapter = FakeExtractor(results)

    @contextmanager
    def factory(*_args: object, **_kwargs: object) -> Iterator[FakeExtractor]:
        yield adapter

    monkeypatch.setattr("datakeel.worker.kg_runner.create_extractor", factory)
    return adapter
