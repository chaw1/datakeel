# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""An edit that names what to edit but not what to change is asked about, never planned.

"把 Mia 的技能改一下" names a person and a kind of change but no new value; a card that
changes nothing would only confuse. Each editing action lists the parameters that count as
a change; when none is given the reply asks which one, in words.
"""

from datakeel.core.intent_models import Clarification
from datakeel.intents.drafts import DraftStep
from datakeel.intents.wording import field_label

# (action, operation or "") -> the parameters that are a change.
CHANGES: dict[tuple[str, str], tuple[str, ...]] = {
    ("manage_users", "update"): ("display_name", "status", "role_ids", "skill_ids", "team_ids"),
    ("manage_users", "update_team"): ("name", "leader_id"),
    ("manage_skills", "update"): ("name", "annotation_type", "domain", "level"),
    ("configure_project", ""): (
        "lease_minutes",
        "dispatch_strategy",
        "skill_requirement",
        "max_active_tasks",
        "clear",
    ),
}
# A change said in other words still counts: role_id for role_ids.
ALSO = {"role_ids": ("role_id",)}


def nothing_to_edit(step: DraftStep) -> tuple[str, ...]:
    """The parameters that could change, when the step gives none of them; else empty."""
    operation = step.params.get("operation")
    changes = CHANGES.get((step.action, operation if isinstance(operation, str) else ""), ())
    given = {
        name
        for name in changes
        for key in (name, *ALSO.get(name, ()))
        if step.params.get(key) not in (None, "")
    }
    return () if given or not changes else changes


def edit_question(step: DraftStep, changes: tuple[str, ...], language: str) -> Clarification:
    """Ask which of the changeable things should change."""
    separator = "、" if language == "zh" else ", "
    labels = separator.join(field_label(name, language) for name in changes)
    question = (
        f"要改哪一项, 改成什么? 可以改: {labels}。"
        if language == "zh"
        else f"What should change, and to what? You can change: {labels}."
    )
    return Clarification(question=question, action=step.action, fields=list(changes))
