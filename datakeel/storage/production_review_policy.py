# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Make every loosening of review a signed decision, never a silent default.

Two configuration changes need a signature: reviewing fewer low-risk submissions, and
starting or widening high-confidence pass-through (a manual bar replacing cold-start
defaults, or any lower bar than the one in force). Tightening either never does.
"""

from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import ConfigureProjectParams
from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.core.prelabel_models import ConfidenceThresholds
from datakeel.core.production_models import Project
from datakeel.storage.production_tasks import require_project
from datakeel.storage.production_tiers import project_thresholds


def lowers_review_sampling(session: Session, params: BoundaryModel) -> bool:
    """Require approval when a configuration would review fewer low-risk submissions."""
    if not isinstance(params, ConfigureProjectParams) or params.review_sample_rate is None:
        return False
    current = require_project(session, params.project_id).review_sample_rate
    return params.review_sample_rate < current


def pass_through_bar(thresholds: ConfidenceThresholds) -> float | None:
    """Return the confidence from which drafts skip annotation, or None while none do."""
    return thresholds.high if thresholds.pass_through else None


def pass_through_change(
    session: Session, params: BoundaryModel
) -> tuple[ConfidenceThresholds, ConfidenceThresholds] | None:
    """Return the thresholds before and after a change that starts or widens pass-through."""
    if not isinstance(params, ConfigureProjectParams):
        return None
    clearing = "confidence_thresholds" in params.clear
    if params.confidence_high is None and not clearing:
        return None
    project = require_project(session, params.project_id)
    low = project.confidence_low if params.confidence_low is None else params.confidence_low
    changed = project.model_copy(
        update={
            "confidence_high": None if clearing else params.confidence_high,
            "confidence_low": None if clearing else low,
        }
    )
    before, after = project_thresholds(session, project), project_thresholds(session, changed)
    old, new = pass_through_bar(before), pass_through_bar(after)
    widened = new is not None and (old is None or new < old)
    return (before, after) if widened else None


def relaxes_pass_through(session: Session, params: BoundaryModel) -> bool:
    """Require approval when a threshold change lets more model drafts skip a person."""
    return pass_through_change(session, params) is not None


def require_ordered_thresholds(project: Project) -> Project:
    """Reject an effective configuration whose low threshold exceeds its high threshold."""
    high, low = project.confidence_high, project.confidence_low
    if high is not None and low is not None and low > high:
        message = "confidence_low must not exceed confidence_high"
        raise ValidationError(message)
    return project
