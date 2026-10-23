# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Revalidate frozen evidence selections without reevaluating mutable review decisions."""

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.actions.parameters import SelectionParams
from datakeel.core.errors import ConflictError
from datakeel.core.models import BoundaryModel
from datakeel.ontology.models import FrozenManifest, ObjectSet, PropertyFilter
from datakeel.storage.action_selection import dataset_id_for
from datakeel.storage.evidence_actions import action_manifest
from datakeel.storage.evidence_snapshot import read_snapshot
from datakeel.storage.object_projection import content_digest
from datakeel.storage.object_queries import evaluate_in_session


def _frozen_evidence_manifest(session: Session, manifest: FrozenManifest) -> FrozenManifest:
    groups: dict[tuple[str, str], list[str]] = {}
    for item in manifest.objects:
        if item.asset_ref.version is None:
            msg = "Frozen evidence targets require exact source versions"
            raise ConflictError(msg)
        key = (dataset_id_for(item), item.asset_ref.version)
        groups.setdefault(key, []).append(item.asset_ref.asset_id)
    snapshot = read_snapshot(session)
    objects = [
        item
        for (dataset_id, version), identifiers in sorted(groups.items())
        for item in evaluate_in_session(
            session,
            ObjectSet(
                schema_version=manifest.query.schema_version,
                object_type=manifest.query.object_type,
                dataset_id=dataset_id,
                version_ids=[version],
                filters=[
                    PropertyFilter.model_validate(
                        {"field": "id", "operator": "in", "value": identifiers}
                    )
                ],
                limit=10000,
            ),
            snapshot,
        ).objects
    ]
    objects.sort(key=lambda item: (item.asset_ref.asset_id, item.asset_ref.version or ""))
    return FrozenManifest(
        query=manifest.query,
        objects=objects,
        total_bytes=sum(item.size for item in objects),
        state_digest=content_digest(
            {
                "query": manifest.query.model_dump(mode="json"),
                "objects": [item.model_dump(mode="json") for item in objects],
            }
        ),
    )


def current_manifest(session: Session, plan: ActionPlan, params: BoundaryModel) -> FrozenManifest:
    """Keep evidence membership frozen while still checking current file facts and state."""
    query = plan.manifest.query
    if isinstance(params, SelectionParams) and (
        query.assertion_filters or query.has_near_duplicate_in is not None
    ):
        return _frozen_evidence_manifest(session, plan.manifest)
    return action_manifest(session, params, query)
