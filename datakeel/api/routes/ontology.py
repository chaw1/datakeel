# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned ontology contracts and reproducible asset selections."""

from fastapi import APIRouter, Request

from datakeel.actions.registry import action_definitions
from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import AssetRef
from datakeel.ontology.models import FrozenManifest, ObjectSet, OntologyRegistry
from datakeel.ontology.registry import registry
from datakeel.storage.data_asset_reads import authorize_query
from datakeel.storage.object_queries import evaluate

router = APIRouter(prefix="/api/ontology", tags=["ontology"])


@router.get("")
def definitions() -> OntologyRegistry:
    """List registered types, relationship semantics, read functions and actions."""
    return registry(action_definitions())


@router.post("/object-sets/evaluate")
def evaluate_objects(body: ObjectSet, db: DatabaseDependency, request: Request) -> FrozenManifest:
    """Freeze the current matching assets with their observed revisions."""
    # Frozen object properties disclose source metadata such as captions, so the
    # selection passes the same query-scope asset guard as the search_files tool.
    manifest = evaluate(db, body)
    refs = [item.asset_ref for item in manifest.objects]
    if body.dataset_id:
        refs.append(AssetRef(asset_id=body.dataset_id))
    authorize_query(
        db,
        tuple(refs),
        AccessContext(
            actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="ask", scope="query"
        ),
    )
    return manifest
