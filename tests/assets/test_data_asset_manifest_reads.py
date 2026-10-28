# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolving many file references reads each version manifest once, not once per file."""

from sqlalchemy import event
from sqlalchemy.engine import Connection

from datakeel.core.models import AssetRef, FileItem
from datakeel.storage.data_asset_native import native_targets
from datakeel.storage.database import Database, DatasetRow, VersionRow

FILES = 40
VERSIONS = 3


def _files() -> list[dict[str, object]]:
    return [
        FileItem(
            id=f"file-{index:03d}",
            filename=f"generated-{index:03d}.txt",
            path=f"generated-{index:03d}.txt",
            size=1,
            sha256="0" * 64,
            modality="text",
        ).model_dump()
        for index in range(FILES)
    ]


def test_file_targets_read_each_manifest_once_per_session(db: Database) -> None:
    """A dataset listing authorizes every file; manifests must not be decoded per file."""
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated", files=_files()))
        session.flush()
        for index in range(VERSIONS):
            session.add(VersionRow(id=f"v{index}", dataset_id="dataset", manifest=_files()))
        session.commit()
    statements: list[str] = []

    def record(_connection: Connection, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        with db.session() as session:
            targets = [
                native_targets(session, AssetRef(asset_type="file", asset_id=f"file-{index:03d}"))
                for index in range(FILES)
            ]
            pinned = native_targets(
                session, AssetRef(asset_type="file", asset_id="file-000", version="v1")
            )
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
    assert all(
        {(item.asset_id, item.version) for item in found}
        == {("dataset", f"v{index}") for index in range(VERSIONS)}
        for found in targets
    )
    assert [(item.asset_id, item.version) for item in pinned] == [("dataset", "v1")]
    manifest_reads = [text for text in statements if "versions.manifest" in text]
    assert len(manifest_reads) == VERSIONS
