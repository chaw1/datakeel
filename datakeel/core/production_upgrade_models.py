# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The signed plan for moving one project to a newer template or label-set version."""

from pydantic import Field

from datakeel.core.models import BoundaryModel


class LabelRename(BoundaryModel):
    """Keep a stable label identity whose display name changed between versions."""

    id: str
    before: str
    after: str


class LabelChanges(BoundaryModel):
    """Compare two label-set versions by stable label identity."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    renamed: tuple[LabelRename, ...] = ()
    changed: tuple[str, ...] = Field(
        default=(), description="Same identity and name, other settings (colour, parent...) differ"
    )


class AttributeChanges(BoundaryModel):
    """Compare template attributes by ``target:key``; ``required`` lists newly required ones."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    required: tuple[str, ...] = Field(
        default=(), description="Fields that are required in the target but were not before"
    )


class UpgradeProblemTask(BoundaryModel):
    """One task whose current revision would fail the target version's submit check."""

    task_id: str
    revision_id: str
    sample_id: str
    state: str
    invalid_objects: int = Field(ge=0)
    problems: tuple[str, ...]


class TemplateUpgradePlan(BoundaryModel):
    """Exact effect of one project upgrade, recomputed when it is signed and executed.

    Existing annotations are each task's current (latest) revision; tasks without a revision
    are not counted as annotated. Objects are classification labels, boxes, polygons and spans.
    An annotation is non-compliant when it would fail the target version's submit-time check
    (published labels, template content rules and required attributes); an object is
    non-compliant when its own label or attributes fail.
    """

    project_id: str
    template_id: str | None
    from_template_version: int | None
    to_template_version: int | None
    label_set_id: str
    from_label_set_version: int
    to_label_set_version: int
    labels: LabelChanges
    attributes: AttributeChanges
    settings_changed: tuple[str, ...] = Field(
        default=(), description="Other template settings that differ, by name"
    )
    task_count: int = Field(ge=0, description="Tasks in the project; all switch versions")
    annotated_task_count: int = Field(ge=0, description="Tasks with a current revision")
    annotation_object_count: int = Field(ge=0)
    invalid_task_count: int = Field(ge=0)
    invalid_object_count: int = Field(ge=0)
    invalid_tasks: tuple[UpgradeProblemTask, ...] = ()
