# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Short Chinese and English wording for questions, refusals and plan summaries."""

from functools import lru_cache

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.intents.rules import full_registry

FIELD_LABELS: dict[str, tuple[str, str]] = {
    "dataset_id": ("数据集", "dataset"),
    "version_id": ("数据集版本", "dataset version"),
    "project_id": ("项目", "project"),
    "package_id": ("任务包", "package"),
    "task_id": ("任务", "task"),
    "task_ids": ("任务", "tasks"),
    "actor": ("要派给的人", "person to assign to"),
    "holder": ("任务现在在谁手里", "current holder"),
    "user_id": ("人员", "person"),
    "label_set_id": ("标签集", "label set"),
    "version": ("标签集版本号", "label set version"),
    "name": ("名称", "name"),
    "labels": ("标签", "labels"),
    "selection": ("要处理的文件", "files to act on"),
    "reason": ("原因", "reason"),
    "model_id": ("模型", "model"),
    "workflow_tier": ("工作流档位", "workflow tier"),
    "revision_id": ("修订", "revision"),
    "decision": ("审核结论", "review decision"),
    "annotation": ("标注内容", "annotation"),
    "files": ("预测文件", "prediction files"),
    "format": ("格式", "format"),
    "checks": ("抽检结果", "inspection results"),
    "role_id": ("角色", "role"),
    "scopes": ("权限范围", "scopes"),
    "standard_codes": ("数据标准", "data standard"),
    "sample_ids": ("样本", "sample files"),
    "role_ids": ("角色", "roles"),
    "skill_id": ("技能", "skill"),
    "skill_ids": ("技能", "skills"),
    "team_id": ("团队", "team"),
    "team_ids": ("团队", "teams"),
    "leader_id": ("组长", "team leader"),
    "operation": ("要做的操作", "operation"),
    "display_name": ("显示名", "display name"),
    "status": ("状态", "status"),
    "package_size": ("每包数量", "package size"),
    "lease_minutes": ("领取时限(分钟)", "lease (minutes)"),
    "max_active_tasks": ("每人同时最多任务数", "max active tasks per person"),
    "dispatch_strategy": ("派单方式", "dispatch strategy"),
    "skill_requirement": ("技能要求", "skill requirement"),
    "guidelines": ("标注说明", "guidelines"),
    "budget": ("预算", "budget"),
    "stage": ("阶段", "stage"),
    "strategy": ("派单方式", "strategy"),
    "label_set_version": ("标签集版本", "label set version"),
    "topic": ("主题", "topic"),
    "language": ("语言", "language"),
    "profile": ("起草方式", "drafting mode"),
    "max_cost_usd": ("费用上限(美元)", "cost cap (USD)"),
    "label_set_ids": ("参考标签集", "reference label sets"),
    "annotation_dataset_ids": ("已有标注的数据集", "annotated datasets"),
    "clear": ("清除的设置", "settings to clear"),
    "group_by": ("分包依据", "group by"),
    "ratio": ("抽检比例", "sample ratio"),
    "method": ("抽检方法", "inspection method"),
    "add_labels": ("新增标签", "labels to add"),
    "remove_labels": ("删除标签", "labels to remove"),
    "assignee": ("负责人", "assignee"),
}


def field_label(field: str, language: str) -> str:
    """Name a parameter the way a person would."""
    zh, en = FIELD_LABELS.get(field, (field, field.replace("_", " ")))
    return zh if language == "zh" else en


@lru_cache(maxsize=1)
def _phrases() -> dict[str, tuple[str, str]]:
    current = full_registry()
    values: dict[str, tuple[str, str]] = {}
    for item in [*current.actions, *current.functions]:
        zh = next(iter(item.phrases.get("zh", [])), item.id)
        en = next(iter(item.phrases.get("en", [])), item.id.replace("_", " "))
        values[item.id] = (zh, en)
    return values


def action_title(action: str, language: str) -> str:
    """The registered spoken name of an action or read function."""
    zh, en = _phrases().get(action, (action, action.replace("_", " ")))
    return zh if language == "zh" else en


def missing_question(action: str, fields: list[str], language: str) -> str:
    """Ask for every missing required value of one step at once."""
    names = [field_label(field, language) for field in fields]
    if language == "zh":
        return f"要{action_title(action, language)}, 还缺: {'、'.join(names)}。请补充。"
    return f"To {action_title(action, language)} I still need: {', '.join(names)}."


def settable(action: str, language: str, limit: int = 8) -> list[str]:
    """Names of the settings an action takes, as a person would call them."""
    model = PARAMETER_TYPES.get(action)
    names = [name for name in (model.model_fields if model else {}) if name != "request_id"]
    return [field_label(name, language) for name in names][:limit]


def unknown_question(action: str, unknown: list[str], language: str) -> str:
    """Say which requested setting this action does not have, and which ones it does."""
    keys = unknown
    options = settable(action, language)
    if language == "zh":
        spoken = "、".join(f"「{field_label(key, language)}」" for key in keys)
        return (
            f"{action_title(action, language)}没有 {spoken} 这项设置, 我不能悄悄忽略它。"
            f"能设置的有: {'、'.join(options)}。你想改的是哪一项?"
        )
    spoken = ", ".join(f'"{field_label(key, language)}"' for key in keys)
    return (
        f"{action_title(action, language)} has no setting {spoken}, and I will not drop it "
        f"silently. It can set: {', '.join(options)}. Which one did you mean?"
    )


def unsupported_text(language: str) -> str:
    """The fixed answer when a sentence maps to no registered action or read function."""
    current = full_registry()
    counts = (len(current.actions), len(current.functions))
    if language == "zh":
        return (
            "这句话我没法变成平台上的操作或查询, 所以什么都没做。平台能做的包括: "
            "建标签集和标注项目、切包派单、收回或改派任务、起草标签集和标注指南、"
            "加人和分配角色技能、跑预标注、隔离或删除文件、发布数据集版本, "
            "以及查询项目进度、工作量、返工率、数据质量等"
            f"(共 {counts[0]} 个动作、{counts[1]} 个查询)。换个说法再试试?"
        )
    return (
        "I cannot turn this into an action or a question on the platform, so nothing was "
        "done. The platform can create label sets and annotation projects, split and assign "
        "work, take back or reassign tasks, draft label sets and guidelines, add people with "
        "roles and skills, run prelabelling, quarantine or delete files, publish dataset "
        "versions, and answer questions on progress, workload, rework and data quality "
        f"({counts[0]} actions, {counts[1]} reads). Could you rephrase?"
    )


def subset_question(language: str) -> str:
    """The sentence names part of the files but the plan would cover all of them."""
    if language == "zh":
        return "你说的是其中一部分文件, 但我没法确定是哪几个。请先选中这些文件, 或说清楚条件。"
    return (
        "You mean only some of the files, but I cannot tell which. Select them first or "
        "describe the condition."
    )


def refusal(action: str, scopes: list[str], language: str) -> str:
    """Name the action and the exact missing permission scopes."""
    joined = ", ".join(scopes)
    if language == "zh":
        return (
            f"你没有权限{action_title(action, language)} ({action}) : 需要权限范围 {joined}, "
            f"你当前的角色里没有。手动操作同样会被拒绝; 请找管理员授予包含 {joined} 的角色。"
        )
    return (
        f"You cannot {action_title(action, language)} ({action}): it needs the scope "
        f"{joined}, which your roles do not grant. Doing it by hand is refused too; "
        f"ask an administrator for a role with {joined}."
    )


def plan_text(count: int, approvals: int, language: str) -> str:
    """Summarise a prepared chain and what the person still has to do."""
    if language == "zh":
        tail = f", 其中 {approvals} 步要签批" if approvals else ""
        return f"已拟好 {count} 步计划{tail}。确认后才会执行; 没确认前什么都不会改。"
    steps = "1 step" if count == 1 else f"{count} steps"
    tail = (
        "; 1 needs a signed approval"
        if approvals == 1
        else f"; {approvals} need a signed approval"
        if approvals
        else ""
    )
    return (
        f"Planned {steps}{tail}. Nothing changes until you confirm; "
        "then each step runs with its own receipt."
    )


def nothing_to_change(kind: str, holder: str, language: str) -> str:
    """Say plainly that a selector matched nothing, so no plan is made."""
    if kind == "tasks" and holder:
        return (
            f"{holder} 手里没有符合条件的任务, 没有要改的。"
            if language == "zh"
            else f"{holder} holds no matching tasks; nothing to change."
        )
    if kind == "tasks":
        return (
            "没有符合条件的任务, 没有要改的。"
            if language == "zh"
            else "No tasks match; nothing to change."
        )
    return (
        "没有找到符合条件的文件, 没有要改的。"
        if language == "zh"
        else "No files match; nothing to change."
    )


def invalid_question(problem: str, language: str) -> str:
    """A value the action rejects, said as a request to change it rather than an error."""
    return (
        f"这个计划还不能执行: {problem}。请改一下说法或补充后再试。"
        if language == "zh"
        else f"This plan cannot run yet: {problem}. Please adjust and try again."
    )


def unknown_labels_question(unknown: list[str], existing: list[str], language: str) -> str:
    """A label the person named is not in the label set: say which ones are."""
    shown = existing[:8]
    if language == "zh":
        return f"标签集里没有「{'、'.join(unknown)}」。现有标签: {'、'.join(shown)}。要改哪一个?"
    return f"The label set has no {', '.join(unknown)}. It has: {', '.join(shown)}. Which one?"
