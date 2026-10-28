# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep image alias identity, legacy human decisions and source replacement compatible."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.models import JsonDocument
from datakeel.kg.aliases import same_as_drafts
from datakeel.kg.cache import extraction_identity
from datakeel.kg.loader import get_profile
from datakeel.storage.evidence_decisions import list_decisions
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.kg_store import get_job
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import (
    image_dataset,
    install_transcriber,
    prepare_image,
    transcript,
    use_profile,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.evidence_drafts import ObservationDraft
    from datakeel.core.evidence_models import AssertionStatus, ExtractorRef
    from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
    from datakeel.core.kg_product import KGEntity
    from datakeel.storage.database import Database


def _legacy_aliases(
    entities: tuple[KGEntity, ...],
    drafts: tuple[ObservationDraft, ...],
    schema: KGSchema,
    extractor: ExtractorRef,
    image_extractor: ExtractorRef | None = None,
) -> tuple[ObservationDraft, ...]:
    return same_as_drafts(entities, drafts, schema, extractor)


def test_image_aliases_when_published_share_image_relation_extractor_identity(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both worker products and final publication select the consent-bound image prompt identity."""
    dataset = image_dataset(db, tmp_path, count=2)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(), transcript("Acme Group uses Widget.")))
    install_adapter(monkeypatch, (pair_result(), pair_result("Acme Group")))
    run = execute_graph(db, prepare_image(db, dataset))
    prepared = get_job(db, run.id).prepared
    expected = extraction_identity(
        prepared.schema_definition, prepared.extraction_profile(image=True), prepared.recording_hash
    )
    pair = next(item for item in list_assertions(db) if item.predicate == "kg.same_as")
    assert pair.extractor == expected
    assert all(item.extractor == expected for item in list_assertions(db))
    assert rebuild_evidence(db).matches


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_image_aliases_when_legacy_reviewed_pair_is_reextracted_preserves_human_decision(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: AssertionStatus
) -> None:
    """Stored P10 pair identities remain readable and cannot lose accepted or rejected authority."""
    dataset = image_dataset(db, tmp_path, count=2)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(), transcript("Acme Group uses Widget.")))
    outputs = (pair_result(), pair_result("Acme Group"))
    install_adapter(monkeypatch, (*outputs, *outputs))
    for module in ("datakeel.worker.kg_report", "datakeel.storage.kg_publication"):
        monkeypatch.setattr(f"{module}.same_as_drafts", _legacy_aliases)
    execute_graph(db, prepare_image(db, dataset))
    pair = next(item for item in list_assertions(db) if item.predicate == "kg.same_as")
    mentions = [item for item in list_assertions(db) if item.predicate == "kg.mentions"]
    assert pair.extractor != mentions[0].extractor
    plan = prepare_action(
        db,
        "decide_assertions",
        JsonDocument(root={"assertion_ids": [pair.id], "status": status}),
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    for module in ("datakeel.worker.kg_report", "datakeel.storage.kg_publication"):
        monkeypatch.setattr(f"{module}.same_as_drafts", same_as_drafts)
    changed = get_profile("fake").model_copy(update={"model": "fixture-v2"})

    def profile(_id: str) -> ExtractionProfile:
        return changed

    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", profile)
    execute_graph(db, prepare_image(db, dataset))
    pairs = [item for item in list_assertions(db) if item.predicate == "kg.same_as"]
    assert len(pairs) == 1
    assert (pairs[0].id, pairs[0].status, pairs[0].extractor) == (pair.id, status, pair.extractor)
    assert all(
        item.action != "invalidate" for item in list_decisions(db) if item.assertion_id == pair.id
    )
    assert rebuild_evidence(db).matches


def test_image_aliases_when_one_source_replaced_retains_other_image_evidence(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Image transcript replacement obeys the same partial-source retention as relations."""
    dataset = image_dataset(db, tmp_path, count=2)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(), transcript("Acme Group uses Widget.")))
    install_adapter(monkeypatch, (pair_result(), pair_result("Acme Group"), pair_result()))
    first = execute_graph(db, prepare_image(db, dataset))
    retained = get_job(db, first.id).documents[1].asset_ref.asset_id
    changed = get_profile("fake").model_copy(update={"model": "fixture-v2"})

    def profile(_id: str) -> ExtractionProfile:
        return changed

    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", profile)
    execute_graph(db, prepare_image(db, dataset, file_ids=[dataset.files[0].id]))
    aliases = [item for item in list_assertions(db) if item.predicate == "kg.same_as"]
    assert len(aliases) == 1
    assert retained in {anchor.asset_ref.asset_id for anchor in aliases[0].anchors}
    assert rebuild_evidence(db).matches
