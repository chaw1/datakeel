# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create attributed evidence for actual changes and failed attempts."""

from datakeel.actions.models import ActionPlan
from datakeel.actions.references import plan_refs
from datakeel.core.models import AssetRef, LineageEvent


def receipt(
    plan: ActionPlan, run_id: str, outputs: list[AssetRef], *, error: str | None = None
) -> LineageEvent:
    """Record the actual outputs, retaining no output claims for failed attempts."""
    refs = {item.asset_id: item for item in plan_refs(plan)}
    for item in plan.manifest.objects:
        dataset_id = item.properties.get("dataset_id")
        if isinstance(dataset_id, str):
            refs[dataset_id] = AssetRef(asset_id=dataset_id)
    dataset_id = plan.canonical_params.get("dataset_id")
    if isinstance(dataset_id, str):
        refs[dataset_id] = AssetRef(asset_id=dataset_id)
    attributed = plan.actor
    if plan.agent_id or plan.session_id:
        attributed = f"agent:{plan.agent_id or 'local'}/session:{plan.session_id or 'local'}"
    published = (
        []
        if error
        else [
            *outputs,
            AssetRef(
                asset_type="action_run",
                asset_id=run_id,
                display_name=plan.action_type,
            ),
        ]
    )
    return LineageEvent(
        idempotency_key=f"action:{plan.id}:run:{run_id}",
        event_type="ACTION_RECEIPT",
        operator=plan.action_type,
        inputs=list(refs.values()),
        outputs=published,
        on_behalf_of=attributed,
        source_module="actions",
        source_ref=run_id,
        params={
            "plan_id": plan.id,
            "plan_digest": plan.plan_digest,
            "actor": plan.actor,
            "session_id": plan.session_id,
        },
        run_state="FAIL" if error else "COMPLETED",
        quality={"error": error} if error else {"object_count": plan.impact.object_count},
    )
