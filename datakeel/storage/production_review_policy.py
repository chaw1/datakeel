# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Make lowering a project's review sample rate a signed decision, never a silent default."""

from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import ConfigureProjectParams
from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.core.production_models import Project
from datakeel.storage.production_tasks import require_project


def lowers_review_sampling(session: Session, params: BoundaryModel) -> bool:
    """Require approval when a configuration would review fewer low-risk submissions."""
    if not isinstance(params, ConfigureProjectParams) or params.review_sample_rate is None:
        return False
    current = require_project(session, params.project_id).review_sample_rate
    return params.review_sample_rate < current


def require_ordered_thresholds(project: Project) -> Project:
    """Reject an effective configuration whose low threshold exceeds its high threshold."""
    high, low = project.confidence_high, project.confidence_low
    if high is not None and low is not None and low > high:
        message = "confidence_low must not exceed confidence_high"
        raise ValidationError(message)
    return project
