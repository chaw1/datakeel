# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze metadata facts without introducing them into file manifests."""

from sqlalchemy.orm import Session

from datakeel.actions.catalog_parameters import (
    CatalogActionParams,
    ImportCatalogParams,
    RestoreCatalogParams,
    UpdateMetricParams,
)
from datakeel.actions.standard_parameters import StandardActionParams
from datakeel.catalog.service import prepare_import
from datakeel.core.catalog_canonical import document_hash
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.errors import NotFoundError
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.ontology.models import FrozenManifest, ObjectSet
from datakeel.storage.catalog_store import lock_catalog, read_snapshot
from datakeel.storage.events import all_events
from datakeel.storage.metric_store import validate_metric_update
from datakeel.storage.standard_changes import next_state, standard_impact


def prepare_catalog_params(session: Session, params: BoundaryModel) -> BoundaryModel:
    """Validate controlled semantics and reflect import snapshots from the server."""
    if isinstance(params, StandardActionParams):
        next_state(session, params)
    if isinstance(params, UpdateMetricParams):
        validate_metric_update(session, params.definition)
    if isinstance(params, ImportCatalogParams):
        snapshot, report = prepare_import(params.request)
        return params.model_copy(
            update={"snapshot": snapshot, "parse_failures": report.parse_failures}
        )
    return params


def catalog_manifest() -> FrozenManifest:
    """Retain the legacy manifest contract with no file or catalog selection."""
    return FrozenManifest(
        query=ObjectSet(), objects=[], total_bytes=0, state_digest=document_hash(JsonDocument({}))
    )


def catalog_state(session: Session) -> str:
    """Bind versions as well as properties so intervening metadata changes invalidate plans."""
    lock_catalog(session)
    return document_hash(JsonDocument(read_snapshot(session).model_dump(mode="json")))


def source_snapshot(session: Session, scope: str, version: int) -> CatalogSnapshot:
    """Read a source's historical snapshot, with version zero denoting its empty initial state."""
    versions = [value for _, value in snapshot_events(all_events(session)) if value.scope == scope]
    if not versions or version > len(versions):
        msg = f"Catalog snapshot not found: {scope}@{version}"
        raise NotFoundError(msg)
    return versions[version - 1] if version else CatalogSnapshot(scope=scope)


def catalog_impact(session: Session, params: BoundaryModel, manifest: FrozenManifest) -> int:
    """Count metadata targets independently from legacy frozen file objects."""
    if isinstance(params, StandardActionParams):
        return standard_impact(session, params)
    if isinstance(params, ImportCatalogParams) and params.snapshot is not None:
        return _scope_impact(session, params.snapshot)
    if isinstance(params, RestoreCatalogParams):
        return _scope_impact(session, source_snapshot(session, params.scope, params.version))
    if isinstance(params, CatalogActionParams):
        return 1
    return len(manifest.objects)


def _scope_impact(session: Session, target: CatalogSnapshot) -> int:
    history = [
        value for _, value in snapshot_events(all_events(session)) if value.scope == target.scope
    ]
    prior = history[-1] if history else CatalogSnapshot(scope=target.scope)
    return len({item.asset_ref.asset_id for item in (*prior.objects, *target.objects)})
