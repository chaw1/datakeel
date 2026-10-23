# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional lineage reads, append operations, and portable exports."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError as ModelValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.models import FileItem, JsonDocument, LineageEvent
from datakeel.lineage.collapse import collapse_graph
from datakeel.lineage.exports import export_croissant, export_openlineage
from datakeel.lineage.models import GraphNode, GraphOverlay, GraphQuery, GraphView
from datakeel.lineage.service import all_events, append_event, graph
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.dataset_service import require_dataset
from datakeel.storage.datasets import dataset_dict
from datakeel.storage.evidence_decisions import assertion_view
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.file_state import FileStateRow, overlay_files

if TYPE_CHECKING:
    from datakeel.core.evidence_models import Assertion


def record_event(db: Database, event: LineageEvent) -> bool:
    """Append an idempotent lineage event in one transaction."""
    with db.session() as session:
        inserted = append_event(session, event)
        session.commit()
        return inserted


def get_graph(
    db: Database,
    asset: str | None = None,
    direction: Literal["both", "upstream", "downstream"] = "both",
    depth: int = 20,
    query: GraphQuery | None = None,
) -> GraphView:
    """Return a bounded projection of the immutable event log."""
    with db.session() as session:
        options = query or GraphQuery(asset=asset, direction=direction, depth=depth)
        assertions: tuple[Assertion, ...] = ()
        if options.include_semantic:
            assertions = tuple(
                assertion_view(row)
                for row in session.scalars(
                    select(AssertionRow)
                    .where(
                        AssertionRow.active.is_(True),
                        AssertionRow.status.in_(["candidate", "accepted"]),
                        AssertionRow.predicate == "near_duplicate_of",
                    )
                    .order_by(AssertionRow.id)
                )
            )
        result = graph(
            all_events(session),
            options.asset_id or options.asset,
            options.direction,
            options.hops if options.hops is not None else options.depth,
            GraphOverlay(
                assertions=assertions,
                catalog=read_snapshot(session) if options.include_catalog else None,
            ),
            None if options.collapse else options.max_nodes,
        )
        if options.collapse:
            result = collapse_graph(result, options.asset_id or options.asset, options.max_nodes)
        states = {state.file_id: state for state in session.scalars(select(FileStateRow))}
        nodes = [
            node.model_copy(
                update={
                    "quarantined": states[node.asset_id].quarantined,
                    "deleted": states[node.asset_id].deleted,
                }
            )
            if node.asset_id in states
            else node
            for node in result.nodes
        ]
        return name_graph(session, result.model_copy(update={"nodes": nodes}))


def export_events(db: Database, dataset_id: str | None = None) -> list[JsonDocument]:
    """Export recorded events, optionally scoped to a dataset lineage component."""
    with db.session() as session:
        events = all_events(session)
        if dataset_id:
            require_dataset(session, dataset_id)
            scoped = {value["event_id"] for value in graph(events, dataset_id)["events"]}
            events = [event for event in events if event.event_id in scoped]
        return [JsonDocument.model_validate(value) for value in export_openlineage(events)]


def export_dataset(db: Database, dataset_id: str | None, base_url: str) -> JsonDocument:
    """Export a dataset manifest as a portable Croissant document."""
    if not dataset_id:
        message = "dataset_id is required for Croissant"
        raise ValidationError(message)
    with db.session() as session:
        row = require_dataset(session, dataset_id)
        data = {
            **dataset_dict(row),
            "base_url": base_url.rstrip("/"),
            "url": base_url.rstrip("/") + f"/api/datasets/{row.id}",
        }
        return JsonDocument.model_validate(
            export_croissant(
                data,
                overlay_files(
                    session, row.id, [FileItem.model_validate(item) for item in row.files]
                ),
            )
        )


def _files(item: FileItem) -> tuple[FileItem, ...]:
    if "evidence_sample" not in item.metadata:
        return (item,)
    try:
        sidecars = sample_sidecars(item)
    except ModelValidationError:
        # Optional read-only enrichment must retain the valid primary filename.
        return (item,)
    return tuple(value for value in (item, sidecars.caption, sidecars.annotation) if value)


def _version_names(session: Session, nodes: list[GraphNode]) -> dict[tuple[str, str | None], str]:
    files = {node.asset_id for node in nodes if node.asset_type in {"file", "artifact"}}
    versions = {node.asset_id for node in nodes if node.asset_type == "version"}
    names: dict[tuple[str, str | None], str] = {}
    if not files and not versions:
        return names
    counts: dict[str, int] = defaultdict(int)
    for version in session.scalars(
        select(VersionRow).order_by(VersionRow.dataset_id, VersionRow.created_at, VersionRow.id)
    ):
        counts[version.dataset_id] += 1
        if version.id in versions:
            created = datetime.fromtimestamp(version.created_at, UTC).strftime("%Y-%m-%d %H:%M UTC")
            names[(version.id, None)] = f"{counts[version.dataset_id]} · {created}"
        if not files:
            continue
        for raw in version.manifest:
            for item in _files(FileItem.model_validate(raw)):
                if item.id in files:
                    names[(item.id, version.id)] = item.filename
                    names[(item.id, None)] = item.filename
    return names


def name_graph(session: Session, view: GraphView) -> GraphView:
    """Enrich visible nodes in a read transaction, preserving graph identity and event data.

    Version ordinals are per dataset, ordered by creation time and stable ID. Their
    language-neutral names leave the localized type prefix to each API consumer.
    Exact-version file names take precedence over the newest available manifest.
    """
    names = _version_names(session, view.nodes)
    dataset_ids = {node.asset_id for node in view.nodes if node.asset_type == "dataset"}
    if dataset_ids:
        names.update(
            ((dataset.id, None), dataset.name)
            for dataset in session.scalars(select(DatasetRow).where(DatasetRow.id.in_(dataset_ids)))
        )
    nodes: list[GraphNode] = []
    for node in view.nodes:
        name = names.get((node.asset_id, node.version), names.get((node.asset_id, None)))
        nodes.append(
            node.model_copy(update={"display_name": name, "label": name}) if name else node
        )
    return view.model_copy(update={"nodes": nodes})
