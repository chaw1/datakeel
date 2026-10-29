# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training tool replays retain the exact grants and source snapshot used by the first read."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.service import create_conversation
from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import ConversationCreate, ToolCall
from datakeel.core.llm_data_governance import TrainingAnalysisRequest, TrainingEvaluationRequest
from datakeel.core.models import AssetRef, JsonDocument, new_id, utcnow
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.conversation_store import get
from datakeel.storage.database import VersionRow
from datakeel.storage.dataset_service import import_paths, list_files, list_versions
from datakeel.storage.governance_service import read_governance
from datakeel.storage.llm_data_evaluations import register_evaluation
from datakeel.storage.llm_data_reads import read_training_result
from datakeel.storage.llm_data_store import analyze_training, training_projection
from tests.assets.entry_helpers import grant, publish, revoke
from tests.storage.llm_data_helpers import seed_training

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from sqlalchemy.orm import Session

    from datakeel.core.data_asset_models import AccessContext
    from datakeel.core.llm_data_governance import TrainingProjection
    from datakeel.core.llm_data_models import TrainingReport, TrainingSource
    from datakeel.core.models import FileItem
    from datakeel.storage.database import Database


def test_cached_training_and_quality_tools_recheck_version_pinned_evaluation_grants(
    db: Database, tmp_path: Path
) -> None:
    """Neither protocol replay nor the Agent shortcut may expose a revoked evaluation result."""
    dataset, _, _ = seed_training(db, tmp_path)
    path = tmp_path / "evaluation.txt"
    path.write_text("Rainforests host diverse wildlife.")
    evaluation_dataset = import_paths(db, "Generated evaluation", [path])
    evaluation = register_evaluation(
        db,
        dataset,
        TrainingEvaluationRequest(
            name="Generated",
            source_dataset_id=evaluation_dataset.id,
            file_ids=(list_files(db, evaluation_dataset.id)[0].id,),
        ),
    )
    run = analyze_training(db, dataset, TrainingAnalysisRequest(evaluation_ids=(evaluation.id,)))
    asset = publish(db, AssetRef(asset_id=evaluation_dataset.id))
    granted = grant(db, asset, "valid", "query")
    assert granted is not None
    conversation = create_conversation(db, ConversationCreate())
    catalog = ToolCatalog(get(db, conversation.id))
    context = ToolCallContext(session_id=conversation.id)
    discovered = catalog.invoke(
        db,
        ToolCall(
            id="discover-training", name="tool_search", arguments=JsonDocument({"query": "SFT"})
        ),
        context,
    )
    assert discovered.status == "SUCCEEDED"
    calls = tuple(
        ToolCall(id=f"cached-{name}", name=name, arguments=JsonDocument({"dataset_id": dataset}))
        for name in ("get_training_quality", "get_quality", "get_report")
    )
    for call in calls:
        first = catalog.invoke(db, call, context)
        assert first.status == "SUCCEEDED", first.error
        assert any(
            ref.asset_id == dataset and ref.version == run.version_id for ref in first.asset_refs
        )
        assert any(
            ref.asset_id == evaluation_dataset.id and ref.version == evaluation.version_id
            for ref in first.asset_refs
        )
        assert (
            invoke_tool(db, call.name, call.arguments, context, call_id=call.id).status
            == "SUCCEEDED"
        )
    revoke(db, granted)
    for call in calls:
        for result in (
            invoke_tool(db, call.name, call.arguments, context, call_id=call.id),
            catalog.invoke(db, call, context),
        ):
            assert result.status == "FAILED"
            assert result.content.root == {}
            assert "apply for access" in (result.error or "")


def test_training_fresh_result_refs_do_not_follow_a_version_added_during_analysis(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A query without an explicit version still binds its returned findings to the first source."""
    from datakeel.core.llm_data_governance import TrainingQualityQuery  # noqa: PLC0415
    from datakeel.llm_data import analyze_sources  # noqa: PLC0415

    path = tmp_path / "fresh.jsonl"
    path.write_text('{"instruction":"Explain winter","output":"Winter is a cold season."}\n')
    dataset = import_paths(db, "Fresh read", [path])
    old = list_versions(db, dataset.id)[0]
    later = new_id()

    def changed(sources: tuple[TrainingSource, ...]) -> TrainingReport:
        report = analyze_sources(sources)
        _new_version(db, dataset.id, old.id, later)
        return report

    monkeypatch.setattr("datakeel.storage.llm_data_reads.analyze_sources", changed)
    result = read_training_result(db, TrainingQualityQuery(dataset_id=dataset.id))
    assert result.report.records == 1
    assert {ref.version for ref in result.asset_refs} == {old.id}
    assert list_versions(db, dataset.id)[-1].id == later


def test_governance_refs_use_the_exact_report_projected_before_a_new_version(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quality values and their replay grants remain attached to the same selected report row."""
    dataset, _, run = seed_training(db, tmp_path)
    later = new_id()

    def changed(
        session: Session,
        dataset_id: str,
        version_id: str,
        files: list[FileItem],
        *,
        access: AccessContext | None = None,
    ) -> TrainingProjection:
        result = training_projection(session, dataset_id, version_id, files, access=access)
        _new_version(db, dataset, run.version_id, later)
        return result

    monkeypatch.setattr("datakeel.storage.governance_service.training_projection", changed)
    result = read_governance(db, dataset)
    assert result.asset_refs
    assert {ref.version for ref in result.asset_refs} == {run.version_id}
    assert list_versions(db, dataset)[-1].id == later


def _new_version(db: Database, dataset_id: str, old_id: str, later: str) -> None:
    with db.session() as session:
        old = session.get(VersionRow, old_id)
        assert old is not None
        session.add(
            VersionRow(
                id=later,
                dataset_id=dataset_id,
                manifest=old.manifest,
                created_at=utcnow().timestamp() + 10,
            )
        )
        session.commit()
