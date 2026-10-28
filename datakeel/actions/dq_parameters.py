# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze quality-rule edits, execution requests, and issue transitions."""

from typing import Literal

from pydantic import Field

from datakeel.core.dq_models import DqRule
from datakeel.core.models import BoundaryModel


class QualityActionParams(BoundaryModel):
    """Identify quality mutations independently from legacy file selections."""


class CreateQualityRuleParams(QualityActionParams):
    """Create a new quality rule after reviewing its complete definition."""

    rule: DqRule


class UpdateQualityRuleParams(QualityActionParams):
    """Replace a rule only at the exact revision reviewed by the caller."""

    rule: DqRule
    expected_revision: int = Field(ge=1)


class DeleteQualityRuleParams(QualityActionParams):
    """Archive a rule while retaining its history and recorded results."""

    rule_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)


class RunQualityRuleParams(QualityActionParams):
    """Queue one bounded read of an existing quality rule."""

    rule_id: str = Field(min_length=1)


class ChangeQualityIssueParams(QualityActionParams):
    """Claim or confirm resolution of the exact displayed issue revision."""

    issue_id: str = Field(min_length=1)
    status: Literal["claimed", "resolved"]
    assignee: str | None = Field(default=None, min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)
