# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training HTTP routes use uploaded references and the real human approval boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.core.models import AssetRef
from tests.asgi_client import TestClient
from tests.assets.entry_helpers import grant, publish
from tests.storage.training_helpers import seed_training

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_training_http_scans_lists_downloads_and_approved_clean_publication(
    db: Database, tmp_path: Path
) -> None:
    """Report previews are redacted and each browser operation reaches durable typed storage."""
    dataset, _, first = seed_training(db, tmp_path)
    with TestClient(create_app(db)) as client:
        root = f"/api/datasets/{dataset}/text-governance"
        listed = client.get(root)
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == first.id
        assert "abc@example.test" not in listed.text
        analysis = client.post(f"{root}/analyze", json={"config": {"sample_limit": 10}})
        assert analysis.status_code == 200, analysis.text
        run = analysis.json()
        assert run["report"]["records"] == 4
        assert client.get(f"/api/training-governance/{run['id']}").json() == run
        ledger = client.get(f"/api/training-governance/{run['id']}/ledger")
        assert ledger.status_code == 200
        assert len(ledger.text.splitlines()) == 4
        assert "abc@example.test" not in ledger.text
        assert "attachment" in ledger.headers["content-disposition"]
        plan = client.post(f"/api/training-governance/{run['id']}/clean").json()
        assert not plan["reversible"]
        assert (
            client.post(
                f"/api/actions/{plan['id']}/execute", json={"plan_digest": plan["plan_digest"]}
            ).status_code
            == 403
        )
        approved = client.post(
            f"/api/approvals/{plan['id']}",
            json={"plan_digest": plan["plan_digest"], "approve": True},
        )
        assert approved.status_code == 200, approved.text
        executed = client.post(
            f"/api/actions/{plan['id']}/execute", json={"plan_digest": plan["plan_digest"]}
        )
        assert executed.status_code == 200, executed.text
        final = client.get(f"/api/training-governance/{run['id']}").json()
        assert final["cleaned_version_id"]
        assert client.get("/api/training-governance/missing").status_code == 404
        assert (
            client.post(
                f"{root}/analyze", json={"path": "/arbitrary/unregistered.jsonl"}
            ).status_code
            == 422
        )


def test_training_http_evaluation_registration_uses_existing_uploaded_files(
    db: Database, tmp_path: Path
) -> None:
    """The browser registers fixture text through dataset/version/file identities only."""
    dataset, _, run = seed_training(db, tmp_path)
    with TestClient(create_app(db)) as client:
        path = f"/api/datasets/{dataset}/text-governance/evaluations"
        assert client.get(path).json() == []
        registered = client.post(
            path,
            json={
                "name": "Fixture",
                "source_dataset_id": dataset,
                "version_id": run.version_id,
                "file_ids": [run.report.files[0].file_id],
            },
        )
        assert registered.status_code == 200, registered.text
        assert client.get(path).json() == [registered.json()]
        excluded = client.post(
            f"/api/datasets/{dataset}/text-governance/analyze",
            json={"evaluation_ids": [registered.json()["id"]]},
        )
        assert excluded.status_code == 422


def test_training_findings_and_ledger_preserve_native_query_and_download_grants(
    db: Database, tmp_path: Path
) -> None:
    """A saved scan cannot become another entry point around the dataset's current policy."""
    dataset, _, run = seed_training(db, tmp_path)
    asset = publish(db, AssetRef(asset_id=dataset))
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "reader"}) as client:
        for path in (
            f"/api/datasets/{dataset}/text-governance",
            f"/api/training-governance/{run.id}",
            f"/api/training-governance/{run.id}/ledger",
        ):
            denied = client.get(path)
            assert denied.status_code == 403
            assert "Rainforests" not in denied.text
        grant(db, asset, "valid", "query", subject="reader")
        assert client.get(f"/api/training-governance/{run.id}").status_code == 200
        assert client.get(f"/api/datasets/{dataset}/text-governance").status_code == 200
        assert client.get(f"/api/training-governance/{run.id}/ledger").status_code == 403
        grant(db, asset, "valid", "download", subject="reader")
        assert client.get(f"/api/training-governance/{run.id}/ledger").status_code == 200
