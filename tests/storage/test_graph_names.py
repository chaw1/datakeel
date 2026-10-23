# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Graph names use authoritative metadata without rewriting immutable history."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.core.evidence_inputs import SampleSidecars
from datakeel.core.models import AssetRef, FileItem, LineageEvent
from datakeel.lineage.models import GraphNode, GraphView
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.events import all_events, append_event
from datakeel.storage.lineage_service import get_graph, name_graph

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _node(kind: str, identity: str, version: str | None = None) -> GraphNode:
    return GraphNode(
        id=identity,
        asset_id=identity,
        asset_type=kind,
        namespace="default",
        label=identity,
        version=version,
    )


def _manifest(filename: str = "val/scene-0817/image.png") -> list[dict[str, object]]:
    return [
        FileItem(
            id="image",
            filename=filename,
            path="/generated/image.png",
            metadata={
                "evidence_sample": SampleSidecars(
                    sample_key=filename,
                    split="val",
                    caption=FileItem(
                        id="caption", filename="val/scene-0817/caption.txt", path="/generated/text"
                    ),
                    annotation=FileItem(
                        id="annotation",
                        filename="val/scene-0817/annotations.json",
                        path="/generated/annotations",
                    ),
                ).model_dump(mode="json")
            },
        ).model_dump(mode="json"),
        FileItem(id="plain", filename="notes.txt", path="/generated/notes.txt").model_dump(),
    ]


def test_graph_names_when_files_have_no_event_names_use_manifests_without_writes(
    db: Database,
) -> None:
    """Resolve image and sidecar names while retaining the exact stored event and manifest."""
    manifest = _manifest()
    event = LineageEvent(
        idempotency_key="name-test",
        operator="generated.observation",
        inputs=[AssetRef(asset_type="file", asset_id="image", version="first")],
        outputs=[
            AssetRef(asset_type="file", asset_id="caption", version="first"),
            AssetRef(asset_type="file", asset_id="annotation", version="first"),
            AssetRef(asset_type="file", asset_id="plain", version="first"),
            AssetRef(asset_type="file", asset_id="missing", version="first"),
        ],
    )
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated scenes", files=manifest))
        session.flush()
        session.add(VersionRow(id="first", dataset_id="dataset", manifest=manifest))
        append_event(session, event)
        session.commit()
    names = {node.asset_id: node.display_name for node in get_graph(db).nodes}
    assert names == {
        "image": "val/scene-0817/image.png",
        "caption": "val/scene-0817/caption.txt",
        "annotation": "val/scene-0817/annotations.json",
        "plain": "notes.txt",
        "missing": None,
    }
    with db.session() as session:
        assert all_events(session) == [event]
        assert session.scalar(select(VersionRow.manifest)) == manifest


def test_graph_names_when_versions_share_files_keep_exact_version_and_dataset_ordinals(
    db: Database,
) -> None:
    """Name versions chronologically per dataset and use the requested manifest's filename."""
    with db.session() as session:
        session.add_all(
            [DatasetRow(id=identity, name=identity) for identity in ("dataset", "other")]
        )
        session.flush()
        session.add_all(
            [
                VersionRow(id="first", dataset_id="dataset", created_at=0, manifest=_manifest()),
                VersionRow(
                    id="second",
                    dataset_id="dataset",
                    created_at=60,
                    manifest=_manifest("val/renamed/image.png"),
                ),
                VersionRow(id="other-first", dataset_id="other", created_at=0, manifest=[]),
            ]
        )
        session.commit()
        view = GraphView(
            nodes=[
                _node("file", "image", "first"),
                _node("file", "image"),
                _node("version", "second", "second"),
                _node("version", "other-first", "other-first"),
                _node("dataset", "dataset"),
                _node("task", "task"),
            ],
            edges=[],
            events=[],
        )
        result = name_graph(session, view)
    assert [node.display_name for node in result.nodes] == [
        "val/scene-0817/image.png",
        "val/renamed/image.png",
        "2 · 1970-01-01 00:01 UTC",
        "1 · 1970-01-01 00:00 UTC",
        "dataset",
        None,
    ]
    assert result.nodes[2].version == "second"
    assert all(node.display_name is None for node in view.nodes)


def test_graph_names_when_only_version_is_visible_does_not_require_file_manifest(
    db: Database,
) -> None:
    """Version-only reads expose a stable ordinal without parsing unrelated file metadata."""
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated scenes"))
        session.flush()
        session.add(VersionRow(id="first", dataset_id="dataset", created_at=0, manifest=[]))
        session.commit()
        result = name_graph(
            session,
            GraphView(nodes=[_node("version", "first")], edges=[], events=[]),
        )
    assert result.nodes[0].display_name == "1 · 1970-01-01 00:00 UTC"


@pytest.mark.parametrize("metadata", ["custom value", {}, None])
@pytest.mark.parametrize("malformed_id", ["visible", "unrelated"])
def test_graph_names_when_optional_sidecars_are_malformed_preserves_primary_names(
    db: Database, metadata: object, malformed_id: str
) -> None:
    """Malformed extension metadata cannot break related or unrelated graph reads."""
    files = [
        FileItem(
            id=identity,
            filename=f"{identity}.txt",
            path=f"/generated/{identity}.txt",
            metadata={"evidence_sample": metadata} if identity == malformed_id else {},
        )
        for identity in ("visible", "unrelated")
    ]
    event = LineageEvent(
        idempotency_key="optional-metadata",
        operator="generated.observation",
        inputs=[AssetRef(asset_type="file", asset_id="visible", version="visible-version")],
    )
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated files"))
        session.flush()
        session.add_all(
            [
                VersionRow(
                    id=f"{item.id}-version",
                    dataset_id="dataset",
                    manifest=[item.model_dump(mode="json")],
                )
                for item in files
            ]
        )
        append_event(session, event)
        session.commit()
    result = get_graph(db, asset="visible")
    assert result.nodes[0].display_name == "visible.txt"
    with db.session() as session:
        stored = session.scalar(
            select(VersionRow.manifest).where(VersionRow.id == f"{malformed_id}-version")
        )
        assert stored[0]["metadata"]["evidence_sample"] == metadata
        assert all_events(session) == [event]
