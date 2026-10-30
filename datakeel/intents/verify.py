# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic checks every plan passes before it becomes a card; no model is involved.

Before filling, a draft must use the action the speaker's verb and role mean (a reviewer's
打回 is a review decision, not a reopen), must not reach a cloud model or spend money the
words never asked for, and must not create a second object when the words name an
existing one. A problem gets one repair round with the model, then a question to the
person. After filling, a plan whose every step changes nothing is not shown: the person
hears that it is already so.
"""

import re

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError
from datakeel.core.intent_models import ChainStep
from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import ProductionLabel
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.drafts import DraftStep, IntentDraft
from datakeel.intents.fill_state import FillState
from datakeel.storage.database import Database
from datakeel.storage.identity_store import get_bindings, list_users
from datakeel.storage.intent_reads import latest_label_set, task_holders
from datakeel.storage.production_queries import get_project, get_task

SEND_BACK = re.compile(
    r"打回|驳回|退回|返工|重做|不合格|send (?:it |this |this task )?back|reject|rework|redo",
    re.IGNORECASE,
)
APPROVE = re.compile(r"通过|合格|没问题|approve|accept|looks good|\bpass\b", re.IGNORECASE)
RELEASE = re.compile(
    r"放回|不做了|还回去|release|give (?:it )?back|put (?:it )?back", re.IGNORECASE
)
MODEL_WORDS = re.compile(
    r"起草|草拟|草稿|草案|预标|模型|自动标|智能|抽取|AI|\bdraft|pre-?label|model|automatic"
    r"|extract",
    re.IGNORECASE,
)
# Asking the platform to come up with labels or rules from sources is asking for a draft.
DRAFT_WORDS = re.compile(
    r"参考|根据|依据|按照|整理|归纳|总结|推荐|建议|生成|想(?:几|一|些)|"
    r"come up with|suggest|propose|generate|based on|according to|from (?:the|these|this)",
    re.IGNORECASE,
)
REPLACE_WORDS = re.compile(
    r"只保留|只要|只留|改成|换成|替换|设为|设成|去掉|删|移除|撤掉|"
    r"\b(?:only|replace|instead|remove|set (?:\w+ )?to)\b",
    re.IGNORECASE,
)
CREATE_WORDS = re.compile(r"新建|新的|创建|建一个|建个|另建|\bcreate\b|\bnew\b", re.IGNORECASE)
WHOLE_WORDS = re.compile(
    r"全部|所有|整个|全都|都|一切|\ball\b|\bevery\w*|\bentire\b|\bwhole\b", re.IGNORECASE
)
# Steps that send data to a cloud model or spend money.
MODEL_ACTIONS = frozenset({"draft_label_set", "run_prelabel", "run_kg_extraction"})
USER_FIELDS = ("status", "display_name", "skill_ids", "team_ids")
PROJECT_FIELDS = ("lease_minutes", "dispatch_strategy", "max_active_tasks", "skill_requirement")


class Problem(BoundaryModel):
    """One rule a draft breaks: a hint for the repair round and a question for the person."""

    code: str
    hint: str
    question_zh: str
    question_en: str

    def question(self, language: str) -> str:
        """The question in the person's language."""
        return self.question_zh if language == "zh" else self.question_en


def says_whole(text: str) -> bool:
    """The words ask for a whole set (全部/所有/all), not a described part of it."""
    return WHOLE_WORDS.search(text) is not None


def _task_state(db: Database, step: DraftStep, state: FillState) -> str | None:
    task = step.params.get("task_id") or state.context.task_id
    if not isinstance(task, str):
        return None
    try:
        return get_task(db, task).state
    except NotFoundError:
        return None


def _review_problem(step: DraftStep, text: str) -> Problem | None:
    decision = step.params.get("decision")
    back, good = SEND_BACK.search(text), APPROVE.search(text)
    if decision == "approve" and back and not good:
        wanted = "rework"
    elif decision == "rework" and good and not back:
        wanted = "approve"
    else:
        return None
    return Problem(
        code="verb",
        hint=f"The person said to {wanted} the task: review_task needs decision={wanted}.",
        question_zh="你是要通过这条, 还是打回返工?",
        question_en="Do you want to approve this task or send it back for rework?",
    )


def _verb_problem(db: Database, step: DraftStep, state: FillState) -> Problem | None:
    """The action must be the one the verb means for this speaker and this task."""
    text = state.text
    if step.action == "review_task":
        return _review_problem(step, text)
    reviewing = step.action == "reopen_task" and SEND_BACK.search(text)
    if reviewing and _task_state(db, step, state) in {"submitted", "in_review"}:
        return Problem(
            code="verb",
            hint="The task is waiting for review: sending it back is review_task with "
            "decision=rework (revision_id may be left out), not reopen_task.",
            question_zh="这条还在审核中: 你是要打回返工吗?",
            question_en="This task is under review: do you want to send it back for rework?",
        )
    if step.action == "revoke_assignment" and RELEASE.search(text):
        holder = task_holders(db, [str(step.params.get("task_id") or state.context.task_id)])
        if state.actor in holder.values():
            return Problem(
                code="verb",
                hint="The speaker gives back their own task: that is release_task, not "
                "revoke_assignment.",
                question_zh="你是要把自己手里的这条放回去吗?",
                question_en="Do you want to give your own task back?",
            )
    return None


def _model_problem(step: DraftStep, text: str) -> Problem | None:
    """A cloud model or spending step needs words that ask for drafting or a model."""
    asked = MODEL_WORDS.search(text) or (
        step.action == "draft_label_set" and DRAFT_WORDS.search(text)
    )
    if step.action not in MODEL_ACTIONS or asked:
        return None
    return Problem(
        code="outbound",
        hint=f"The person did not ask to draft, pre-label or use a model; {step.action} "
        "sends data to a model and may cost money. Use the plain action instead (for a "
        "label set with named labels: create_label_set).",
        question_zh="这一步会把数据发给模型并可能产生费用, 但你没说要用模型。要用模型做吗?",
        question_en="This step would send data to a model and may cost money, but you did "
        "not ask for a model. Should a model do it?",
    )


def _duplicate_problem(step: DraftStep, text: str, catalog: EntityCatalog) -> Problem | None:
    """Creating an object named like an existing one, when the words do not say new."""
    if step.action != "create_label_set" or "label_set_id" in step.params:
        return None
    name = step.params.get("name")
    found = catalog.match("label_set", name) if isinstance(name, str) else []
    exact = [entry for entry in found if isinstance(name, str) and name in entry.names]
    if not exact or CREATE_WORDS.search(text):
        return None
    label = exact[0].label
    return Problem(
        code="reference",
        hint=f"The person refers to the existing label set {name}: change it with "
        "label_set_id and add_labels/remove_labels/rename_labels instead of creating one.",
        question_zh=f"要改现有的「{label}」, 还是另建一个同名的新标签集?",
        question_en=f'Change the existing "{label}", or create a new label set with that name?',
    )


def _role_problem(step: DraftStep) -> Problem | None:
    """An account update never changes roles; binding a role is its own operation."""
    params = step.params
    roles = params.get("role_id") or params.get("role_ids")
    if step.action != "manage_users" or params.get("operation") != "update" or not roles:
        return None
    return Problem(
        code="ineffective",
        hint="operation=update does not change roles: give a role with operation=bind_role "
        "and role_id (one step per role, project_id for one project); take one away with "
        "unbind_role.",
        question_zh="你是要给这个人加上这个角色吗? 请说一下角色和项目。",
        question_en="Do you want to give this person that role? Please name the role and project.",
    )


def _dropped_problem(db: Database, step: DraftStep, text: str) -> Problem | None:
    """A full skill or team list that silently drops what the person did not mention."""
    if step.action != "manage_users" or step.params.get("operation") != "update":
        return None
    wanted = step.params.get("user_id")
    user = next(
        (item for item in list_users(db) if wanted in {item.id, item.display_name}),
        None,
    )
    if user is None or REPLACE_WORDS.search(text):
        return None
    for field, held in (("skill_ids", user.skill_ids), ("team_ids", user.team_ids)):
        listed = step.params.get(field)
        given = {str(item) for item in listed} if isinstance(listed, list) else None
        lost = [item for item in held if given is not None and item not in given]
        if lost:
            adding = field.replace("_ids", "")
            return Problem(
                code="lost",
                hint=f"{field} replaces the whole list and would drop {', '.join(lost)}, which "
                f"the person did not ask to remove: use add_{field} (or remove_{field}).",
                question_zh=f"这样会去掉 {user.display_name} 现有的{adding}: {'、'.join(lost)}。"
                "是要追加, 还是替换掉原有的?",
                question_en=f"This would remove {user.display_name}'s current {adding}s "
                f"({', '.join(lost)}). Add to them, or replace them?",
            )
    return None


def draft_problems(
    db: Database, draft: IntentDraft, state: FillState, catalog: EntityCatalog
) -> list[Problem]:
    """Every rule the draft breaks, checked before permissions and filling."""
    found: list[Problem] = []
    for step in draft.steps:
        problem = (
            _verb_problem(db, step, state)
            or _model_problem(step, state.text)
            or _duplicate_problem(step, state.text, catalog)
            or _dropped_problem(db, step, state.text)
            or _role_problem(step)
        )
        if problem is not None:
            found.append(problem)
    return found


def _labels(values: JsonValue) -> list[dict[str, JsonValue]]:
    items = values if isinstance(values, list) else []
    return [
        ProductionLabel.model_validate(item).model_dump(mode="json", exclude_none=True)
        for item in items
    ]


def _label_set_unchanged(db: Database, params: dict[str, JsonValue]) -> bool:
    label_set = params.get("label_set_id")
    current = latest_label_set(db, label_set) if isinstance(label_set, str) else None
    if current is None or params.get("migration") or params.get("operation") == "delete":
        return False
    before = [label.model_dump(mode="json", exclude_none=True) for label in current.labels]
    renamed = params.get("name") not in (None, current.name)
    return not renamed and "guidelines" not in params and _labels(params.get("labels")) == before


def _published(db: Database, params: dict[str, JsonValue]) -> bool:
    label_set, version = params.get("label_set_id"), params.get("version")
    if not isinstance(label_set, str) or not isinstance(version, int):
        return False
    found = latest_label_set(db, label_set, version)
    return found is not None and found.published


def _same(current: JsonValue, wanted: JsonValue) -> bool:
    if isinstance(current, (list, tuple)) and isinstance(wanted, list):
        return sorted(map(str, current)) == sorted(map(str, wanted))
    return current == wanted


def _user_unchanged(db: Database, params: dict[str, JsonValue]) -> bool:
    user = next((item for item in list_users(db) if item.id == params.get("user_id")), None)
    if user is None:
        return False
    operation = params.get("operation")
    if operation == "bind_role":
        return any(
            binding.role_id == params.get("role_id")
            and binding.project_id == params.get("project_id")
            for binding in get_bindings(db, user.id)
        )
    current = user.model_dump(mode="json")
    given = [field for field in USER_FIELDS if field in params]
    return (
        operation == "update"
        and bool(given)
        and all(_same(current[field], params[field]) for field in given)
    )


def _project_unchanged(db: Database, params: dict[str, JsonValue]) -> bool:
    project = params.get("project_id")
    if not isinstance(project, str) or params.get("clear"):
        return False
    try:
        current = get_project(db, project).model_dump(mode="json")
    except NotFoundError:
        return False
    given = [field for field in PROJECT_FIELDS if field in params]
    return bool(given) and all(_same(current[field], params[field]) for field in given)


def _assigned_already(db: Database, params: dict[str, JsonValue]) -> bool:
    tasks, actor = params.get("task_ids"), params.get("actor")
    if not isinstance(tasks, list) or not tasks or not isinstance(actor, str):
        return False
    if params.get("stage", "annotation") != "annotation":
        return False
    holders = task_holders(db, [str(task) for task in tasks])
    return all(holders.get(str(task)) == actor for task in tasks)


def unchanged(db: Database, step: ChainStep) -> bool:
    """The step would leave everything exactly as it is."""
    checks = {
        "create_label_set": _label_set_unchanged,
        "publish_label_set": _published,
        "manage_users": _user_unchanged,
        "configure_project": _project_unchanged,
        "assign_tasks": _assigned_already,
    }
    check = checks.get(step.action)
    return check is not None and not step.items and check(db, step.params)
