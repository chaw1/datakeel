# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""AI pre-review at submission: P26 suspicion rules, the project template and draft agreement.

The score and every reason are stored against the submitted revision. In group and team
projects a high-risk submission is always reviewed; a low-risk one is reviewed when its
reproducible draw falls under the project's review sample rate (100% by default, so every
submission is reviewed as before) and is otherwise approved with an audit note. Personal
projects only record the result for the annotator to see; nothing is blocked.

Risk is recomputed when the evidence changes, not only at submission: when a head is scored,
every near-duplicate partner still waiting for review is rescored against it and, if its
reasons changed, gets a new append-only review row for the same revision with the original
decision and draw. Both the review queue and the task view read the newest row, so they show
the same recomputed reasons, and the history keeps every earlier score.
"""

from sqlalchemy.orm import Session

from datakeel.annotation_qa import HIGH_RISK, risk_score, sample_draw
from datakeel.core.models import new_id, utcnow
from datakeel.core.prelabel_models import AIReview, RiskReason
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.storage.production_ai_facts import load_facts
from datakeel.storage.production_ai_rows import ProductionAIReviewRow, latest_reviews
from datakeel.storage.production_ai_rules import head_reasons
from datakeel.storage.production_assignments import finish_assignment
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_tasks import transition_task

EXEMPT_NOTE = "AI 预审低风险，按抽检比例免审 / AI pre-review low risk, exempt by review sampling"  # noqa: RUF001  # The audit wording is specified in Chinese.
RESCORE_NOTE = (
    "近重复图片有新提交，风险已重算 / Risk recomputed after a near-duplicate image was submitted"  # noqa: RUF001  # Reviewer-facing wording is bilingual.
)
_WAITING = ("submitted", "in_review")


def _store(session: Session, review: AIReview) -> None:
    session.add(
        ProductionAIReviewRow(
            id=review.id,
            task_id=review.task_id,
            project_id=review.project_id,
            revision_id=review.revision_id,
            risk=review.risk,
            payload=review.model_dump(mode="json"),
        )
    )


def _rescore(session: Session, previous: AIReview, reasons: list[RiskReason]) -> None:
    """Append a new review of the same head when its reasons changed; decisions stay."""
    if tuple(reasons) == previous.reasons:
        return
    risk = risk_score(reasons)
    review = previous.model_copy(
        update={
            "id": new_id(),
            "risk": risk,
            "high_risk": risk >= HIGH_RISK,
            "reasons": tuple(reasons),
            "note": RESCORE_NOTE,
            "created_at": utcnow(),
        }
    )
    _store(session, AIReview.model_validate(review.model_dump()))


def _score_with_partners(
    session: Session, project: Project, task: ProductionTaskRow, head: AnnotationRevision
) -> list[RiskReason]:
    """Score the head, then rescore waiting near-duplicate partners that now see this head."""
    facts = load_facts(session, project, task)
    own = facts.tasks[task.id]
    facts.tasks[task.id] = own._replace(head=head)
    reasons, partners = head_reasons(session, project, facts, task.id, head)
    for partner in partners:
        item = facts.tasks[partner]
        if item.head is not None and item.state in _WAITING:
            partner_reasons, _ = head_reasons(session, project, facts, partner, item.head)
            current = latest_reviews(session, (partner,)).get(partner)
            if current is not None and current.revision_id == item.head.id:
                _rescore(session, current, partner_reasons)
    return reasons


def prereview(
    session: Session, project: Project, task: ProductionTaskRow, head: AnnotationRevision
) -> AIReview:
    """Score the submitted head, decide review or exemption, and store the evidence."""
    reasons = _score_with_partners(session, project, task, head)
    risk = risk_score(reasons)
    draw = sample_draw(task.id, task.round, head.id)
    high = risk >= HIGH_RISK
    rate = project.review_sample_rate
    if project.workflow_tier == "personal":
        decision, note = "personal", ""
    elif high or draw < rate:
        decision, note = "review", ""
    else:
        decision = "exempt"
        note = f"{EXEMPT_NOTE}: sample_rate={rate:.4g}, risk={risk:.4f}, draw={draw:.4f}"
    review = AIReview.model_validate(
        {
            "id": new_id(),
            "project_id": project.id,
            "task_id": task.id,
            "revision_id": head.id,
            "round": task.round,
            "risk": risk,
            "high_risk": high,
            "reasons": reasons,
            "sample_rate": rate,
            "draw": draw,
            "decision": decision,
            "note": note,
            "created_at": utcnow(),
        }
    )
    _store(session, review)
    if decision == "exempt":
        task.approved_revision_id = task.latest_revision_id
        finish_assignment(session, task.id, "annotation", "approved")
        transition_task(session, task, "approved")
    return review
