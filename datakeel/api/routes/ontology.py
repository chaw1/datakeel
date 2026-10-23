# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned ontology contracts and reproducible asset selections."""

from fastapi import APIRouter

from datakeel.actions.registry import action_definitions
from datakeel.api.dependencies import DatabaseDependency
from datakeel.ontology.models import FrozenManifest, ObjectSet, OntologyRegistry
from datakeel.ontology.registry import registry
from datakeel.storage.object_queries import evaluate

router = APIRouter(prefix="/api/ontology", tags=["ontology"])


@router.get("")
def definitions() -> OntologyRegistry:
    """List registered types, relationship semantics, read functions and actions."""
    return registry(action_definitions())


@router.post("/object-sets/evaluate")
def evaluate_objects(body: ObjectSet, db: DatabaseDependency) -> FrozenManifest:
    """Freeze the current matching assets with their observed revisions."""
    return evaluate(db, body)
