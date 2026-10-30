# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""What each planned step changes, costs and whether a person must sign it."""

from pydantic import JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.actions.registry import POLICIES
from datakeel.core.intent_models import ChainStep, StepEstimate
from datakeel.intents.catalog import EntityCatalog
from datakeel.ontology.models import ObjectSet
from datakeel.storage.database import Database
from datakeel.storage.label_drafts import planned_draft_cost
from datakeel.storage.object_queries import evaluate

GOVERNANCE = frozenset(
    {
        "import_standards",
        "update_standard",
        "update_code_list",
        "confirm_standard_mapping",
        "rollback_standards",
        "confirm_metric_draft",
    }
)
SINGLE = frozenset(
    {
        "publish_label_set",
        "configure_project",
        "upgrade_project",
        "define_role",
        "update_role",
        "register_model",
        "update_model",
        "finalize_project",
    }
)


def _version_size(step: ChainStep, catalog: EntityCatalog) -> int | None:
    version = step.params.get("version_id")
    entry = catalog.get("version", version) if isinstance(version, str) else None
    return entry.size if entry else None


def _selection_size(db: Database, step: ChainStep) -> int | None:
    raw = step.params.get("selection")
    if not isinstance(raw, dict):
        return None
    try:
        return len(evaluate(db, ObjectSet.model_validate(raw)).objects)
    except (ModelValidationError, ValueError):
        return None


def _length(value: JsonValue) -> int | None:
    return len(value) if isinstance(value, list) else None


def _count(
    db: Database, step: ChainStep, catalog: EntityCatalog, previous: list[ChainStep]
) -> int | None:
    params = step.params
    direct = (
        len(step.items) if step.items else None,
        _length(params.get("task_ids")),
        _length(params.get("labels")) if step.action == "create_label_set" else None,
        1 if step.action in SINGLE or "task_id" in params else None,
        _length(params.get("sample_ids")) or 0 if step.action == "draft_label_set" else None,
    )
    found = next((value for value in direct if value is not None), None)
    if found is not None:
        return found
    if step.action == "create_project":
        return _version_size(step, catalog)
    if step.action == "split_packages":
        created = next((item for item in previous if item.action == "create_project"), None)
        return created.estimate.object_count if created else None
    return _selection_size(db, step)


def estimate_step(
    db: Database, step: ChainStep, catalog: EntityCatalog, previous: list[ChainStep]
) -> StepEstimate:
    """Bound a step before it is prepared; preparation later freezes the exact impact."""
    _, reversible, _ = POLICIES[step.action]
    external = step.action == "draft_label_set" and step.params.get("profile") not in {
        None,
        "offline",
    }
    cost = 0.0
    if step.action == "draft_label_set":
        cost = planned_draft_cost(db, step.params)
    return StepEstimate(
        object_count=_count(db, step, catalog, previous),
        cost_usd=cost,
        requires_approval=not reversible or external or step.action in GOVERNANCE,
        external=external,
    )
