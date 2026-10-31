# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Values a step's words leave to the state: a role's project, an asset or files by name.

A role given to someone who works in projects belongs to this page's project or their only
one, else the person is asked; "码头照片" in a lineage question is the one object of any
kind with that name; sample files picked by name are those files' identities.
"""

from pydantic import JsonValue

from datakeel.core.intent_models import Clarification
from datakeel.intents.catalog import EntityCatalog, candidates
from datakeel.intents.drafts import DraftStep
from datakeel.intents.fill_state import FillState, ask, context_value
from datakeel.intents.object_edits import bound_projects
from datakeel.storage.database import Database

# Kinds a lineage or other any-kind asset identity may name.
ASSET_KINDS = ("dataset", "version", "label_set", "project", "model")


def role_project(
    db: Database,
    params: dict[str, JsonValue],
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
) -> Clarification | None:
    """A role for someone who works in projects: this page's project, their only one, or ask."""
    bound = bound_projects(db, params) if current.action == "manage_users" else []
    page = context_value("project_id", state, catalog)
    if not bound or page is not None or len(bound) == 1:
        if bound:
            params["project_id"] = page or bound[0]
        return None
    offered = [entry for entry in catalog.of("project") if entry.id in bound]
    return ask("project_id", current, candidates(offered), state.language)


def any_asset(value: str, catalog: EntityCatalog) -> str:
    """An asset said by its name ("码头照片") is the one object of any kind with that name."""
    if any(entry.id == value for entry in catalog.entries):
        return value
    found = [entry for kind in ASSET_KINDS for entry in catalog.match(kind, value)]
    wanted = value.strip().casefold()
    exact = [entry for entry in found if wanted in {name.casefold() for name in entry.names}]
    chosen = exact or found
    return chosen[0].id if len(chosen) == 1 else value


def sample_files(params: dict[str, JsonValue]) -> None:
    """Sample files picked by name are those files' ids, read from the dataset that has them."""
    chosen = params.get("sample_ids")
    filters = chosen.get("filters") if isinstance(chosen, dict) else None
    if not isinstance(chosen, dict) or not isinstance(filters, list):
        return
    for condition in filters:
        if isinstance(condition, dict) and condition.get("field") == "id":
            params["sample_ids"] = condition.get("value")
            params.setdefault("dataset_id", chosen.get("dataset_id"))
