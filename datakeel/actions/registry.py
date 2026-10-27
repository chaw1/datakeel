# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declare built-in action policies separately from their execution handlers."""

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.ontology.models import ActionType

POLICIES: dict[str, tuple[str, bool, str]] = {
    "quarantine_files": ("files:write", True, "Set quarantine state"),
    "unquarantine_files": ("files:write", True, "Clear quarantine state"),
    "create_version_from_selection": (
        "datasets:write",
        True,
        "Publish manifest",
    ),
    "run_pipeline": (
        "pipelines:run",
        True,
        "Schedule durable processing",
    ),
    "save_metadata": (
        "datasets:write",
        True,
        "Replace validated metadata",
    ),
    "delete_files": ("files:delete", False, "Logically delete selected files"),
    "export_dataset": ("datasets:export", False, "Publish an approved local export artifact"),
    "decide_assertions": ("evidence:write", True, "Review assertion status with append-only audit"),
    "import_catalog": ("catalog:write", True, "Publish a versioned source snapshot"),
    "confirm_metric_draft": ("metrics:write", True, "Confirm imported semantic draft"),
    "restore_catalog": ("catalog:write", True, "Restore a prior source snapshot"),
    "update_metric": ("metrics:write", True, "semantic_change"),
    "rollback_metric": ("metrics:write", True, "semantic_change"),
    "update_term": ("terms:write", True, "semantic_change"),
    "rollback_term": ("terms:write", True, "semantic_change"),
    "run_kg_extraction": ("kg:extract", True, "Extract candidate graph facts with source evidence"),
}


def action_definition(action_type: str) -> ActionType:
    """Resolve a declared action's schemas, required scope, and reversibility."""
    policy = POLICIES.get(action_type)
    if policy is None:
        msg = f"Unknown action: {action_type}"
        raise ValidationError(msg)
    scope, reversible, effect = policy
    return ActionType(
        id=action_type,
        params_schema=JsonDocument.model_validate(PARAMETER_TYPES[action_type].model_json_schema()),
        auth_scope=scope,
        preconditions=[
            "frozen target revisions match",
            "authorized limits",
            *(["metric catalog references resolve"] if action_type == "update_metric" else []),
        ],
        effects=[effect],
        reversible=reversible,
        inverse_of={
            "quarantine_files": "unquarantine_files",
            "unquarantine_files": "quarantine_files",
            "decide_assertions": "decide_assertions",
            "import_catalog": "restore_catalog",
            "restore_catalog": "import_catalog",
            "update_metric": "rollback_metric",
            "rollback_metric": "update_metric",
            "update_term": "rollback_term",
            "rollback_term": "update_term",
        }.get(action_type),
        handler=f"datakeel.actions.execute:{action_type}",
    )


def action_definitions() -> list[ActionType]:
    """List versioned policies used by ontology and tool discovery."""
    return [action_definition(name) for name in POLICIES]
