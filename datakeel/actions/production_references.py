# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve production parameter identities without confusing worker and annotation tasks."""

from datakeel.actions.identity_parameters import IdentityActionParams
from datakeel.actions.production_catalog_parameters import ProductionCatalogActionParams
from datakeel.actions.production_parameters import ProductionActionParams
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument


def production_parameter_refs(params: BoundaryModel) -> list[AssetRef]:
    """Bind target, parent and source references to the displayed controlled plan."""
    if not isinstance(
        params, IdentityActionParams | ProductionCatalogActionParams | ProductionActionParams
    ):
        return []
    values = JsonDocument.model_validate(params.model_dump(mode="json")).root
    kinds = {
        "project_id": "project",
        "package_id": "task_package",
        "task_id": "production_task",
        "revision_id": "annotation_revision",
        "previous_revision_id": "annotation_revision",
        "label_set_id": "label_set",
        "template_id": "template",
        "model_id": "model",
        "user_id": "user",
        "role_id": "role",
        "team_id": "team",
        "skill_id": "skill",
        "dataset_id": "dataset",
        "version_id": "version",
    }
    label_version = values.get("label_set_version", values.get("version"))
    refs = [
        AssetRef(
            asset_type=kind,
            asset_id=identifier,
            version=str(label_version)
            if kind == "label_set" and isinstance(label_version, int)
            else identifier
            if kind == "version"
            else None,
        )
        for key, kind in kinds.items()
        if isinstance(identifier := values.get(key), str)
    ]
    task_ids = values.get("task_ids")
    if isinstance(task_ids, list):
        refs.extend(
            AssetRef(asset_type="production_task", asset_id=identifier)
            for identifier in task_ids
            if isinstance(identifier, str)
        )
    for key, kind in (("template", "template"), ("model", "model")):
        nested = values.get(key)
        if isinstance(nested, dict) and isinstance(identifier := nested.get("id"), str):
            refs.append(AssetRef(asset_type=kind, asset_id=identifier))
    return refs
