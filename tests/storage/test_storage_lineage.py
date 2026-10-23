# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for storage lineage."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datakeel.storage.database import Database

from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from datakeel.core.models import AssetRef, LineageEvent
from datakeel.lineage.service import all_events, append_event, graph
from datakeel.storage.database import EventRow, VersionRow
from datakeel.storage.datasets import import_dataset, materialize_files
from datakeel.storage.objects import LocalStore, S3Store


def test_manifest_is_content_addressed_and_import_is_replayable(
    db: Database, tmp_path: Path
) -> None:
    """Verify manifest is content addressed and import is replayable."""
    source = tmp_path / "note.txt"
    source.write_text("generated content")
    with db.session() as session:
        dataset = import_dataset(session, "notes", [source])
        session.commit()
        version = session.scalar(select(VersionRow))
        assert version.manifest[0]["sha256"]
        original = version.manifest[0]["sha256"]
        source.write_text("changed source")
        assert version.manifest[0]["sha256"] == original
        assert Path(materialize_files(dataset.files)[0].path).read_text() == "generated content"


def test_events_idempotent_immutable_and_graph_depth(db: Database) -> None:
    """Verify events idempotent immutable and graph depth."""
    event = LineageEvent(
        idempotency_key="one",
        operator="file.dedup",
        inputs=[AssetRef(asset_id="a")],
        outputs=[AssetRef(asset_id="b")],
    )
    second = LineageEvent(
        idempotency_key="two",
        operator="image.resize",
        inputs=[AssetRef(asset_id="b")],
        outputs=[AssetRef(asset_id="c")],
    )
    with db.session() as session:
        assert append_event(session, event)
        assert not append_event(session, event.model_copy(update={"event_id": "different"}))
        append_event(session, second)
        session.commit()
        assert session.scalar(select(func.count()).select_from(EventRow)) == 2
        assert len(graph(all_events(session), "a", "downstream", 1)["nodes"]) == 2
        assert len(graph(all_events(session), "c", "upstream", 2)["nodes"]) == 3
        assert not graph(all_events(session), "missing")["nodes"]
    for sql in (
        "DELETE FROM lineage_events",
        "UPDATE lineage_events SET idempotency_key='changed'",
    ):
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text(sql))


def test_local_store_rejects_escape(tmp_path: Path) -> None:
    """Verify local store rejects escape."""
    store = LocalStore(tmp_path / "store")
    with pytest.raises(ValueError, match="Invalid object key"):
        store.materialize("../outside")


def test_s3_backend_roundtrip_with_client_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify s3 backend roundtrip with client contract."""
    objects = {}

    class Client:
        def upload_file(self, filename: str, bucket: str, key: str) -> None:
            """Provide the upload file test fixture."""
            objects[(bucket, key)] = Path(filename).read_bytes()

        def download_file(self, bucket: str, key: str, filename: str) -> None:
            """Provide the download file test fixture."""
            Path(filename).write_bytes(objects[(bucket, key)])

    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr("datakeel.storage.objects.boto3.client", lambda *_a, **_k: Client())
    source = tmp_path / "text.txt"
    source.write_text("s3 sample")
    store = S3Store("test-bucket")
    store.put(source, "aa/text.txt")
    assert store.materialize("aa/text.txt").read_text() == "s3 sample"
