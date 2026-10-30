# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Plan and execute a signed move of one project to newer template and label versions.

The plan compares the locked and target versions and checks each task's current revision
against the target's submit-time rules. Nothing changes until the plan is signed; execution
recomputes the plan and only rewrites this project's version lock, never a revision.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import UpgradeProjectTemplateParams
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.production_attributes import attribute_problems
from datakeel.core.production_catalog_models import LabelSet, ProductionTemplate
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.core.production_upgrade_models import (
    AttributeChanges,
    LabelChanges,
    LabelRename,
    TemplateUpgradePlan,
    UpgradeProblemTask,
)
from datakeel.storage.production_catalog import require_label_set, validate_template_content
from datakeel.storage.production_rows import (
    ProductionProjectRow,
    ProductionRevisionRow,
    ProductionTaskRow,
)
from datakeel.storage.production_tasks import require_mutable_project
from datakeel.storage.production_template_versions import (
    latest_label_set_version,
    latest_template,
    locked_template,
    template_version,
)

_SETTINGS = ("name", "annotation_type", "validation_rules")


def _label_changes(before: LabelSet, after: LabelSet) -> LabelChanges:
    old = {label.id: label for label in before.labels}
    new = {label.id: label for label in after.labels}
    shared = sorted(old.keys() & new.keys())
    return LabelChanges(
        added=tuple(sorted(new.keys() - old.keys())),
        removed=tuple(sorted(old.keys() - new.keys())),
        renamed=tuple(
            LabelRename(id=key, before=old[key].name, after=new[key].name)
            for key in shared
            if old[key].name != new[key].name
        ),
        changed=tuple(
            key for key in shared if old[key].name == new[key].name and old[key] != new[key]
        ),
    )


def _attribute_changes(
    before: ProductionTemplate | None, after: ProductionTemplate | None
) -> AttributeChanges:
    old = {f"{item.target}:{item.key}": item for item in (before.attributes if before else ())}
    new = {f"{item.target}:{item.key}": item for item in (after.attributes if after else ())}
    shared = sorted(old.keys() & new.keys())
    return AttributeChanges(
        added=tuple(sorted(new.keys() - old.keys())),
        removed=tuple(sorted(old.keys() - new.keys())),
        changed=tuple(key for key in shared if old[key] != new[key]),
        required=tuple(
            sorted(
                key
                for key, item in new.items()
                if item.required and (key not in old or not old[key].required)
            )
        ),
    )


def _settings_changes(
    before: ProductionTemplate | None, after: ProductionTemplate | None
) -> tuple[str, ...]:
    if before is None or after is None:
        return ()
    changed = [name for name in _SETTINGS if getattr(before, name) != getattr(after, name)]
    keys = sorted(before.component_config.keys() | after.component_config.keys())
    changed.extend(
        f"component_config.{key}"
        for key in keys
        if before.component_config.get(key) != after.component_config.get(key)
    )
    return tuple(changed)


def annotation_problems(
    labels: LabelSet, template: ProductionTemplate | None, annotation: AnnotationRecord
) -> tuple[tuple[str, ...], int]:
    """Return every submit-time failure and how many objects fail on their own label/fields."""
    allowed = {value for label in labels.labels for value in (label.id, label.name)}
    fields = template.attributes if template else ()
    shaped = [field for field in fields if field.target == "object"]
    problems: list[str] = []
    invalid = 0
    for index, value in enumerate(annotation.labels or (), start=1):
        if value not in allowed:
            problems.append(f'Label {index} "{value}" is not in label set v{labels.version}')
            invalid += 1
    for kind, shapes in (
        ("box", annotation.boxes),
        ("polygon", annotation.polygons),
        ("span", annotation.spans),
    ):
        for index, shape in enumerate(shapes or (), start=1):
            issues = list(attribute_problems(shaped, shape.attributes, f"{kind} {index}"))
            if shape.category not in allowed:
                issues.insert(
                    0,
                    f'{kind} {index} label "{shape.category}" is not in label set '
                    f"v{labels.version}",
                )
            invalid += bool(issues)
            problems.extend(issues)
    record = [field for field in fields if field.target == "record"]
    problems.extend(attribute_problems(record, annotation.attributes, "the record"))
    if template is not None:
        try:
            validate_template_content(template, annotation)
        except ValidationError as error:
            problems.append(str(error))
    return tuple(problems), invalid


def _objects(annotation: AnnotationRecord) -> int:
    return sum(
        len(values or ())
        for values in (annotation.labels, annotation.boxes, annotation.polygons, annotation.spans)
    )


def _targets(
    session: Session, project: Project, params: UpgradeProjectTemplateParams
) -> tuple[ProductionTemplate | None, ProductionTemplate | None, LabelSet, LabelSet]:
    before = locked_template(session, project)
    after = before
    if project.template_id is None:
        if params.template_version is not None:
            message = "This project has no template to upgrade"
            raise ValidationError(message)
    else:
        revision = params.template_version or latest_template(session, project.template_id).revision
        after = template_version(session, project.template_id, revision)
        if after.archived:
            message = f"Template version {revision} is archived; choose an earlier version"
            raise ValidationError(message)
        if before is not None and after.revision < before.revision:
            message = "Template downgrades are not supported"
            raise ValidationError(message)
    label_target = (
        params.label_set_version
        or latest_label_set_version(session, project.label_set_id)
        or project.label_set_version
    )
    if label_target < project.label_set_version:
        message = "Label-set downgrades are not supported"
        raise ValidationError(message)
    labels_before = require_label_set(session, project.label_set_id, project.label_set_version)
    labels_after = require_label_set(session, project.label_set_id, label_target)
    unchanged = (before is None or after is None or before.revision == after.revision) and (
        labels_after.version == labels_before.version
    )
    if unchanged:
        message = "The project already uses these template and label-set versions"
        raise ValidationError(message)
    return before, after, labels_before, labels_after


def upgrade_plan(session: Session, params: UpgradeProjectTemplateParams) -> TemplateUpgradePlan:
    """Compute the exact, reviewable effect of upgrading one unfinalized project."""
    project = require_mutable_project(session, params.project_id)
    before, after, labels_before, labels_after = _targets(session, project, params)
    tasks = list(
        session.scalars(
            select(ProductionTaskRow)
            .where(ProductionTaskRow.project_id == project.id)
            .order_by(ProductionTaskRow.id)
        )
    )
    annotated = objects = invalid_objects = 0
    invalid: list[UpgradeProblemTask] = []
    for task in tasks:
        row = session.get(ProductionRevisionRow, task.latest_revision_id or "")
        if row is None:
            continue
        annotation = AnnotationRevision.model_validate(row.payload).annotation
        annotated += 1
        objects += _objects(annotation)
        problems, failing = annotation_problems(labels_after, after, annotation)
        if problems:
            invalid_objects += failing
            invalid.append(
                UpgradeProblemTask(
                    task_id=task.id,
                    revision_id=row.id,
                    sample_id=task.sample_id,
                    state=task.state,
                    invalid_objects=failing,
                    problems=problems,
                )
            )
    return TemplateUpgradePlan(
        project_id=project.id,
        template_id=project.template_id,
        from_template_version=before.revision if before else None,
        to_template_version=after.revision if after else None,
        label_set_id=project.label_set_id,
        from_label_set_version=labels_before.version,
        to_label_set_version=labels_after.version,
        labels=_label_changes(labels_before, labels_after),
        attributes=_attribute_changes(before, after),
        settings_changed=_settings_changes(before, after),
        task_count=len(tasks),
        annotated_task_count=annotated,
        annotation_object_count=objects,
        invalid_task_count=len(invalid),
        invalid_object_count=invalid_objects,
        invalid_tasks=tuple(invalid),
    )


def upgrade_project_template(
    session: Session, params: UpgradeProjectTemplateParams
) -> tuple[Project, TemplateUpgradePlan]:
    """Move only this project's locks; revisions, states and other projects stay untouched."""
    row = session.get(
        ProductionProjectRow, params.project_id, with_for_update=True, populate_existing=True
    )
    plan = upgrade_plan(session, params)
    project = require_mutable_project(session, params.project_id)
    upgraded = project.model_copy(
        update={
            "template_version": plan.to_template_version,
            "label_set_version": plan.to_label_set_version,
        }
    )
    if row is not None:
        row.payload = upgraded.model_dump(mode="json")
    session.flush()
    return upgraded, plan
