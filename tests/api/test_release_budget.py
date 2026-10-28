# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Large releases and versions request an explicit, capped budget that the user approves."""

from pathlib import Path

import pytest
from sqlalchemy import select

from datakeel.api.app import create_app
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import import_paths
from tests.api.release_budget_helpers import FILES, GIB, large_version
from tests.asgi_client import TestClient


def _release(dataset: str, version: str, tag: str) -> dict[str, str]:
    return {"dataset_id": dataset, "version_id": version, "tag": tag}


def test_default_budget_refuses_large_release_and_explains_the_explicit_budget(
    db: Database, tmp_path: Path
) -> None:
    """Without a requested budget the 10,000-object default applies, with a usable hint."""
    dataset, version = large_version(db, tmp_path)
    with TestClient(create_app(db)) as client:
        refused = client.post(
            "/api/actions/publish_release/prepare", json=_release(dataset, version, "1.0.0")
        )
    assert refused.status_code == 422
    assert "exceeds the authorized object or byte budget" in refused.json()["detail"]
    assert "max_objects" in refused.json()["detail"]


def test_explicit_budget_within_ceiling_is_frozen_approved_and_executed(
    db: Database, tmp_path: Path
) -> None:
    """The requested budget is part of the digest-bound plan the local user approves."""
    dataset, version = large_version(db, tmp_path)
    with TestClient(create_app(db)) as client:
        prepared = client.post(
            "/api/actions/publish_release/prepare",
            params={"max_objects": 20_000, "max_bytes": 2 * GIB},
            json=_release(dataset, version, "1.0.0"),
        )
        assert prepared.status_code == 200, prepared.text
        plan = prepared.json()
        assert plan["context"]["max_objects"] == 20_000
        assert plan["context"]["max_bytes"] == 2 * GIB
        assert plan["impact"]["object_count"] == FILES
        approved = client.post(
            f"/api/approvals/{plan['id']}",
            json={"approve": True, "plan_digest": plan["plan_digest"]},
        )
        assert approved.status_code == 200, approved.text
        run = client.post(
            f"/api/actions/{plan['id']}/execute", json={"plan_digest": plan["plan_digest"]}
        )
        assert run.status_code == 200, run.text
        release = run.json()["receipt"]["outputs"][0]["asset_id"]
        assert client.get(f"/api/releases/{release}").json()["file_count"] == FILES


def test_budget_above_ceiling_or_for_other_actions_is_rejected(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requests above the configured ceiling, and budgets on ordinary actions, are refused."""
    dataset, version = large_version(db, tmp_path)
    with TestClient(create_app(db)) as client:
        above = client.post(
            "/api/actions/publish_release/prepare",
            params={"max_objects": 1_000_001},
            json=_release(dataset, version, "1.0.0"),
        )
        assert above.status_code == 422
        assert "above the ceiling" in above.json()["detail"]
        assert "DATAKEEL_RELEASE_BUDGET_MAX_OBJECTS" in above.json()["detail"]
        too_large = client.post(
            "/api/actions/publish_release/prepare",
            params={"max_bytes": 1024**4 + 1},
            json=_release(dataset, version, "1.0.0"),
        )
        assert too_large.status_code == 422
        other = client.post(
            "/api/actions/delete_files/prepare",
            params={"max_objects": 20_000},
            json={"selection": {"dataset_id": dataset}},
        )
        assert other.status_code == 422
        assert "only for" in other.json()["detail"]
        assert (
            client.post(
                "/api/actions/publish_release/prepare",
                params={"max_objects": 0},
                json=_release(dataset, version, "1.0.0"),
            ).status_code
            == 422
        )
        monkeypatch.setenv("DATAKEEL_RELEASE_BUDGET_MAX_OBJECTS", "15000")
        lowered = client.post(
            "/api/actions/publish_release/prepare",
            params={"max_objects": 20_000},
            json=_release(dataset, version, "1.0.0"),
        )
        assert lowered.status_code == 422
        assert "15000" in lowered.json()["detail"]
        within = client.post(
            "/api/actions/publish_release/prepare",
            params={"max_objects": 12_000},
            json=_release(dataset, version, "1.0.0"),
        )
        assert within.status_code == 200, within.text


def test_plan_above_a_lowered_ceiling_cannot_be_approved_or_executed(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lowering the ceiling after preparation stops the frozen plan at its next check."""
    dataset, version = large_version(db, tmp_path)
    with TestClient(create_app(db)) as client:
        plan = client.post(
            "/api/actions/publish_release/prepare",
            params={"max_objects": 20_000},
            json=_release(dataset, version, "1.0.0"),
        ).json()
        monkeypatch.setenv("DATAKEEL_RELEASE_BUDGET_MAX_OBJECTS", "15000")
        approved = client.post(
            f"/api/approvals/{plan['id']}",
            json={"approve": True, "plan_digest": plan["plan_digest"]},
        )
        assert approved.status_code == 422
        assert "current ceiling" in approved.json()["detail"]
        assert client.get("/api/datasets/" + dataset + "/releases").json() == []


def test_selected_version_budget_covers_large_byte_totals(db: Database, tmp_path: Path) -> None:
    """A version of a few very large files needs a byte budget above the 10 GiB default."""
    paths = [tmp_path / f"video-{index}.bin" for index in range(3)]
    for path in paths:
        path.write_bytes(b"generated")
    created = import_paths(db, "large-version", paths)
    with db.session() as session:
        row = session.scalar(select(VersionRow).where(VersionRow.dataset_id == created.id))
        assert row is not None
        row.manifest = [{**item, "size": 6 * GIB} for item in row.manifest]
        session.commit()
    body = {"selection": {"dataset_id": created.id}, "name": "large-selection"}
    with TestClient(create_app(db)) as client:
        refused = client.post("/api/actions/create_version_from_selection/prepare", json=body)
        assert refused.status_code == 422
        prepared = client.post(
            "/api/actions/create_version_from_selection/prepare",
            params={"max_bytes": 20 * GIB},
            json=body,
        )
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["impact"]["total_bytes"] == 18 * GIB
    assert prepared.json()["context"]["max_bytes"] == 20 * GIB
