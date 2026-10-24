# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read graph history stored before consent payloads switched to source fingerprints."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from datakeel.core.kg_models import Recording, RecordingRecord
from datakeel.kg.loader import get_profile
from datakeel.storage.kg_queries import explain_relation, get_source_text
from datakeel.storage.kg_rows import KGRunRow
from datakeel.storage.kg_store import get_job, list_runs
from tests.kg.helpers import graph_product, seed_graph
from tests.kg.integration_helpers import pair_result

if TYPE_CHECKING:
    from datakeel.storage.database import Database


@pytest.mark.parametrize("provider", ["fake", "ollama"])
@pytest.mark.parametrize("has_recording", [False, True])
def test_legacy_run_payload_preserves_source_explanation_without_rewriting_history(
    db: Database, provider: str, *, has_recording: bool
) -> None:
    """Historical source and replay content remain readable after their storage shape changes."""
    product, source = graph_product()
    assertions = seed_graph(db, product, source)
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    recording = Recording(
        model="fixture-model",
        recorded_at="2026-10-24",
        prompt_version="legacy-fixture",
        source="generated fixture",
        records=(
            RecordingRecord(
                **pair_result().model_dump(),
                text_hash=source.content_revision,
                original={"private_recording": "Generated original response"},
            ),
        ),
    )
    with db.session() as session:
        row = session.get(KGRunRow, relation.run_id)
        assert row is not None
        payload = deepcopy(row.payload)
        payload["prepared"]["documents"] = payload.pop("documents")
        payload["prepared"]["recording"] = (
            recording.model_dump(mode="json") if has_recording else None
        )
        if provider == "ollama":
            payload["prepared"]["profile"] = get_profile("ollama").model_dump(mode="json")
            payload["prepared"]["profile"]["request_parameters"]["num_ctx"] = 8192
        row.payload = payload
        session.commit()
    job = get_job(db, relation.run_id)
    assert job.documents[0].text == source.text
    assert job.prepared.documents[0].blocks[0].content_hash == source.content_revision
    assert source.text not in job.prepared.model_dump_json()
    assert "Generated original response" not in job.prepared.model_dump_json()
    assert "num_ctx" not in job.prepared.profile.request_parameters
    assert list_runs(db)[0] == job.run
    assert get_source_text(db, source.file.asset_id, source.dataset_version_id).text == source.text
    assert explain_relation(db, relation.id).sources[0].text == source.text
    with db.session() as session:
        row = session.get(KGRunRow, relation.run_id)
        assert row is not None
        assert row.payload == payload


def test_current_run_cannot_use_legacy_read_compatibility_to_allow_removed_parameters(
    db: Database,
) -> None:
    """Current fingerprint payloads keep the strict profile parameter allowlist."""
    product, source = graph_product()
    assertions = seed_graph(db, product, source)
    run_id = assertions[0].run_id
    with db.session() as session:
        row = session.get(KGRunRow, run_id)
        assert row is not None
        payload = deepcopy(row.payload)
        payload["prepared"]["profile"]["request_parameters"]["num_ctx"] = 8192
        row.payload = payload
        session.commit()
    with pytest.raises(ValidationError, match="unsupported parameter name"):
        get_job(db, run_id)
