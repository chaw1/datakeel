# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze supplementary facts that affect exports beyond selected file revisions."""

import hashlib
import json

from sqlalchemy.orm import Session

from datakeel.actions.catalog_parameters import CatalogActionParams
from datakeel.actions.dq_parameters import QualityActionParams
from datakeel.actions.models import ActionPlan
from datakeel.actions.parameters import DecideAssertionsParams, ExportParams
from datakeel.core.models import BoundaryModel
from datakeel.core.settings import get_settings
from datakeel.lineage.service import graph
from datakeel.ontology.models import FrozenManifest, ObjectSet
from datakeel.storage.action_targets import current_manifest
from datakeel.storage.catalog_action_state import catalog_state
from datakeel.storage.dq_actions import quality_state
from datakeel.storage.events import all_events
from datakeel.storage.evidence_actions import decision_snapshot
from datakeel.storage.object_queries import evaluate_in_session


def snapshot_digest(session: Session, params: BoundaryModel, manifest: FrozenManifest) -> str:
    """Bind selected contents plus dataset metadata and exported event observations."""
    values = [manifest.state_digest]
    if isinstance(params, QualityActionParams):
        values.append(quality_state(session, params))
    if isinstance(params, CatalogActionParams):
        values.append(catalog_state(session))
    if isinstance(params, DecideAssertionsParams):
        values.append(decision_snapshot(session, params))
    if isinstance(params, ExportParams):
        dataset = evaluate_in_session(
            session,
            ObjectSet(
                object_type="dataset",
                dataset_id=params.dataset_id,
                schema_version=manifest.query.schema_version,
            ),
        )
        values.extend([dataset.state_digest, get_settings().base_url])
        if params.format == "openlineage":
            values.append(
                json.dumps(
                    [
                        event.model_dump(mode="json")
                        for event in graph(all_events(session), params.dataset_id).events
                    ],
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def current_snapshot_digest(session: Session, plan: ActionPlan, params: BoundaryModel) -> str:
    """Recheck frozen evidence targets or the legacy query plus supplementary export state."""
    return snapshot_digest(session, params, current_manifest(session, plan, params))
