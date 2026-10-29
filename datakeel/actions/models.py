# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable controlled-action plans, authorization contexts, and receipts."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.kg_execution import KGEstimate
from datakeel.core.kg_images import TranscriptionEstimate
from datakeel.core.models import AssetRef, BoundaryModel, LineageEvent
from datakeel.ontology.models import FrozenManifest

ActionName = Literal[
    "create_data_asset",
    "update_data_asset",
    "publish_data_asset",
    "withdraw_data_asset",
    "decide_asset_application",
    "revoke_asset_grant",
    "quarantine_files",
    "unquarantine_files",
    "create_version_from_selection",
    "run_pipeline",
    "save_metadata",
    "delete_files",
    "export_dataset",
    "decide_assertions",
    "import_catalog",
    "confirm_metric_draft",
    "restore_catalog",
    "update_metric",
    "rollback_metric",
    "update_term",
    "rollback_term",
    "run_kg_extraction",
    "submit_custom_operator",
    "publish_release",
    "import_standards",
    "update_standard",
    "update_code_list",
    "confirm_standard_mapping",
    "rollback_standards",
    "create_quality_rule",
    "update_quality_rule",
    "delete_quality_rule",
    "run_quality_rule",
    "change_quality_issue",
    "annotation_acceptance",
    "generate_datasheet",
    "publish_datasheet",
    "clean_training_data",
]
PlanStatus = Literal["PREPARED", "APPROVED", "REJECTED", "EXECUTED", "FAILED"]
RunStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "DENIED"]


class ActionContext(BoundaryModel):
    """Declare the local actor, tool attribution, and enforced request limits."""

    actor: str = "local"
    agent_id: str | None = None
    session_id: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["*"])
    max_objects: int = Field(default=10000, ge=0)
    max_bytes: int = Field(default=10_737_418_240, ge=0)
    ttl_seconds: int = Field(default=900, ge=1, le=3600)


class ActionImpact(BoundaryModel):
    """Quantify exactly the frozen affected objects and outbound bytes."""

    object_count: int
    total_bytes: int
    external: bool
    kg_estimate: KGEstimate | None = Field(default=None, exclude_if=lambda value: value is None)
    transcription_estimate: TranscriptionEstimate | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class ActionPlan(BoundaryModel):
    """Bind canonical parameters and selected revisions to a single-use plan."""

    id: str
    operation_id: str | None = None
    action_type: ActionName
    canonical_params: dict[str, JsonValue]
    manifest: FrozenManifest
    plan_digest: str
    target_digest: str
    state_digest: str
    created_at: datetime
    expires_at: datetime
    reversible: bool
    external: bool
    impact: ActionImpact
    actor: str
    agent_id: str | None = None
    session_id: str | None = None
    context: ActionContext
    status: PlanStatus = "PREPARED"

    @property
    def requires_approval(self) -> bool:
        """Gate irreversible, outbound, standards and metric-draft changes on human review."""
        return (
            not self.reversible
            or self.external
            or self.action_type
            in {
                "import_standards",
                "update_standard",
                "update_code_list",
                "confirm_standard_mapping",
                "rollback_standards",
                "confirm_metric_draft",
            }
        )


class ApprovalDecision(BoundaryModel):
    """Bind a human decision to the exact displayed plan digest."""

    approve: bool
    plan_digest: str
    actor: str = "local"
    reason: str = ""


class ExecuteRequest(BoundaryModel):
    """Bind an execution to its digest, caller, and optional replay identity."""

    plan_digest: str
    canonical_params: dict[str, JsonValue] | None = None
    actor: str = "local"
    operation_id: str | None = Field(default=None, min_length=1, max_length=200)


class ActionRun(BoundaryModel):
    """Expose durable short execution or asynchronous worker completion."""

    id: str
    plan_id: str
    action_type: ActionName
    status: RunStatus
    created_at: datetime
    completed_at: datetime | None = None
    task_id: str | None = None
    receipt: LineageEvent | None = None
    error: str | None = None
    reason: str | None = Field(
        default=None,
        description=(
            "DENIED explanation: human approval is missing, rejected, or already consumed. "
            "The legacy error field remains available."
        ),
    )


class OperationResult(BoundaryModel):
    """Transfer business changes into the transaction's audit and receipt."""

    outputs: list[AssetRef] = Field(default_factory=list[AssetRef])
    task_id: str | None = None
    generated_file: Path | None = None
    generated_inode: int | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)


class WorkerDecision(BoundaryModel):
    """Allow a queued shard only while its frozen action target remains valid."""

    allowed: bool = True
    error: str | None = None
