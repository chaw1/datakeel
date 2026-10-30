# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Short Chinese and English wording for questions, refusals and plan summaries."""

from functools import lru_cache

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
    tail = f"; {approvals} need a signed approval" if approvals else ""
    return (
        f"Planned {count} step(s){tail}. Nothing changes until you confirm; "
        "then each step runs with its own receipt."
    )
