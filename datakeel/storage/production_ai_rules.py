# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Score one submitted head against project-wide facts: template, P26 rules, draft, near-dups.

P26 rules run over one record per sample (the submitted head, or the draft standing in for a
task nobody has submitted yet) with the template's ``label_mode`` and exclusive label groups,
so size outliers and multi-select conflicts work with one annotator per sample. Near-duplicate
images are compared by the memoised perceptual hash for every image template.
"""

from typing import Literal

from sqlalchemy.orm import Session

from datakeel.annotation_qa import (
    Neighbour,
    agrees_with_draft,
    draft_reasons,
    find_suspicions,
    finding_reason,
    near_duplicate_reason,
)
from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.prelabel_models import RiskReason
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.storage.production_ai_facts import ProjectFacts, hamming_threshold
from datakeel.storage.production_catalog import require_complete_attributes, validate_annotation
from datakeel.storage.production_task_images import sample_hash

_TEMPLATE_ZH = "提交内容不符合项目当前模板的要求，请按模板修改后再提交"  # noqa: RUF001  # Chinese punctuation is intended.
_GROUP_SIZE = 2


def template_reasons(
    session: Session, project: Project, annotation: AnnotationRecord
) -> list[RiskReason]:
    """Recheck the submitted head against the project's current template."""
    try:
        validate_annotation(session, project, annotation, complete=True)
        require_complete_attributes(session, project, annotation)
    except ValidationError as error:
        return [
            RiskReason(
                code="template_violation", weight=0.9, message=str(error), message_zh=_TEMPLATE_ZH
            )
        ]
    return []


def _policy(
    template: ProductionTemplate | None,
) -> tuple[Literal["auto", "single", "multi"], tuple[tuple[str, ...], ...]]:
    config = template.component_config if template is not None else {}
    mode = config.get("label_mode")
    raw = config.get("exclusive_label_groups")
    groups = tuple(
        tuple(dict.fromkeys(value for value in group if isinstance(value, str)))
        for group in (raw if isinstance(raw, list) else ())
        if isinstance(group, list)
    )
    label_mode: Literal["auto", "single", "multi"] = (
        "single" if mode == "single" else "multi" if mode == "multi" else "auto"
    )
    return label_mode, tuple(group for group in groups if len(group) >= _GROUP_SIZE)


def finding_reasons(
    facts: ProjectFacts, task_id: str, record: AnnotationRecord
) -> list[RiskReason]:
    """Run the P26 rules on one record per sample and keep the hits on this task's sample."""
    own = facts.tasks[task_id]
    records = {own.sample_id: record.model_copy(update={"annotator_id": "submitted"})}
    for item in facts.tasks.values():
        source = item.head.annotation if item.head else item.draft.record if item.draft else None
        if source is not None and item.sample_id not in records:
            records[item.sample_id] = source.model_copy(update={"annotator_id": "submitted"})
    label_mode, groups = _policy(facts.template)
    batch = AnnotationBatch(
        annotations=tuple(records.values()), label_mode=label_mode, exclusive_label_groups=groups
    )
    return [
        finding_reason(item, record, facts.names)
        for item in find_suspicions(batch)
        if item.sample_id == own.sample_id
    ]


def near_duplicates(facts: ProjectFacts, task_id: str, record: AnnotationRecord) -> list[str]:
    """List tasks with a submitted head whose image nearly duplicates this task's image."""
    own = facts.tasks[task_id]
    key = facts.keys.get(own.sample_id)
    value = sample_hash(key) if key is not None and record.image_width is not None else None
    if value is None:
        return []
    threshold = hamming_threshold()
    result: list[str] = []
    for item in facts.tasks.values():
        other = facts.keys.get(item.sample_id)
        if item.task_id == task_id or item.head is None or other is None:
            continue
        candidate = sample_hash(other)
        if candidate is not None and (value ^ candidate).bit_count() <= threshold:
            result.append(item.task_id)
    return result


def _near_duplicate_reasons(
    facts: ProjectFacts, task_id: str, record: AnnotationRecord, partners: list[str]
) -> list[RiskReason]:
    neighbours: list[Neighbour] = []
    for partner in partners:
        item = facts.tasks[partner]
        if item.head is not None:
            annotation = item.head.annotation
            name = facts.files.get(item.sample_id, "another image")
            neighbours.append(
                Neighbour(annotation, agrees_with_draft(item.draft, annotation), name)
            )
    agrees = agrees_with_draft(facts.tasks[task_id].draft, record)
    reason = near_duplicate_reason(record, neighbours, agrees=agrees)
    return [reason] if reason is not None else []


def head_reasons(
    session: Session, project: Project, facts: ProjectFacts, task_id: str, head: AnnotationRevision
) -> tuple[list[RiskReason], list[str]]:
    """Return every reason for one head and the near-duplicate tasks it was compared with."""
    record = head.annotation
    draft = facts.tasks[task_id].draft
    partners = near_duplicates(facts, task_id, record)
    reasons = [
        *template_reasons(session, project, record),
        *finding_reasons(facts, task_id, record),
        *(draft_reasons(draft, record, facts.names) if draft and head.source == "human" else []),
        *_near_duplicate_reasons(facts, task_id, record, partners),
    ]
    return reasons, partners
