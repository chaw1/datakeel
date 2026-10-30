# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Effective confidence thresholds per project and the tier routing of fresh model drafts.

Personal projects only show the tier. In group and team projects a pending task whose new
draft is high goes straight to review submission (where AI pre-review and review sampling
decide what a person sees), medium keeps the draft for correction, and low keeps the draft
for viewing while the workbench starts the person from an empty annotation.
"""

from sqlalchemy.orm import Session

from datakeel.annotation_qa import calibrate, task_tier
from datakeel.core.prelabel_models import ConfidenceThresholds, ConfidenceTier, TaskTier
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.storage.production_prelabel_refs import (
    approved_references,
    confidence_observations,
    object_confidences,
)
from datakeel.storage.production_rows import ProductionTaskRow


def project_thresholds(session: Session, project: Project) -> ConfidenceThresholds:
    """Configured thresholds win; otherwise calibrate on approved data or use defaults."""
    observations = confidence_observations(approved_references(session, project.id))
    return calibrate(observations, (project.confidence_high, project.confidence_low))


def revision_tier(revision: AnnotationRevision, thresholds: ConfidenceThresholds) -> ConfidenceTier:
    """Tier one model draft by its lowest object, a draft without objects being low."""
    return task_tier(object_confidences(revision), thresholds.high, thresholds.low)


def route_tier(project: Project, task: ProductionTaskRow, tier: ConfidenceTier) -> TaskTier:
    """Decide what the tier changes; only untouched group/team tasks change flow."""
    if project.workflow_tier == "personal" or task.state != "pending":
        routed = "hint"
    elif tier == "high":
        routed = "submitted"
    elif tier == "medium":
        routed = "draft"
    else:
        routed = "scratch"
    return TaskTier(task_id=task.id, sample_id=task.sample_id, tier=tier, routed=routed)
