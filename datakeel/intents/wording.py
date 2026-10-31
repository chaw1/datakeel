# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Short Chinese and English wording for questions, refusals and plan summaries."""

import re
from collections.abc import Mapping
from functools import lru_cache

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.intents.field_names import ENUM_LABELS, MORE_LABELS
from datakeel.intents.rules import full_registry
from datakeel.intents.scope_words import scope_words

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
    "rename_labels": ("改名", "labels to rename"),
    "add_skill_ids": ("要加的技能", "skills to add"),
    "remove_skill_ids": ("要去掉的技能", "skills to remove"),
    "add_team_ids": ("要加入的团队", "teams to join"),
    "remove_team_ids": ("要退出的团队", "teams to leave"),
    "annotation_type": ("标注类型", "annotation type"),
    "domain": ("领域", "domain"),
    "level": ("等级", "level"),
}


def field_label(field: str, language: str) -> str:
    """Name a parameter the way a person would."""
    zh, en = FIELD_LABELS.get(field) or MORE_LABELS.get(field, (field, field.replace("_", " ")))
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
    # Each value is asked for once, by its plain name.
    names = list(dict.fromkeys(field_label(field, language) for field in fields))
    if language == "zh":
        return f"要{action_title(action, language)}, 还缺: {'、'.join(names)}。请补充。"
    return f"To {action_title(action, language)} I still need: {', '.join(names)}."


def settable(action: str, language: str, limit: int = 8) -> list[str]:
    """Names of the settings an action takes, as a person would call them."""
    model = PARAMETER_TYPES.get(action)
    names = [name for name in (model.model_fields if model else {}) if name != "request_id"]
    return [field_label(name, language) for name in names][:limit]


def _spoken(key: str, value: object, language: str) -> str:
    """A setting the action lacks, by its plain name, else by the value the person gave."""
    label = field_label(key, language)
    if label != key:
        return label
    if isinstance(value, str | int | float) and not isinstance(value, bool):
        return str(value)
    return "你说的某一项" if language == "zh" else "one of the values you gave"


def unknown_question(action: str, unknown: Mapping[str, object], language: str) -> str:
    """Say which requested setting this action does not have, and which ones it does.

    A name the model made up is not repeated back: the setting is named by its plain name,
    or by the value the person said (每包 20 张 reads as 「20」).
    """
    spoken = list(dict.fromkeys(_spoken(key, value, language) for key, value in unknown.items()))
    options = settable(action, language)
    if language == "zh":
        named = "、".join(f"「{item}」" for item in spoken)
        return (
            f"{action_title(action, language)}没有 {named} 对应的设置, 我不能悄悄忽略它。"
            f"能设置的有: {'、'.join(options)}。你想改的是哪一项?"
        )
    named = ", ".join(f'"{item}"' for item in spoken)
    return (
        f"{action_title(action, language)} has no setting for {named}, and I will not drop it "
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
    """Name the action and the missing permission scopes in words.

    The exact scope ids travel in ``missing_scopes``; English text also names them.
    """
    joined = scope_words(scopes, language)
    if language == "zh":
        return (
            f"你没有权限{action_title(action, language)}: 缺少{joined}权限, "
            f"你当前的角色里没有。手动操作同样会被拒绝; 请找管理员给你一个带{joined}权限的角色。"
        )
    return (
        f"You cannot {action_title(action, language)}: it needs the permission for "
        f"{joined}, which your roles do not grant. Doing it by hand is refused too; "
        "ask an administrator for a role that has it."
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
            f"{holder}{'' if holder == '你' else ' '}手里没有符合条件的任务, 没有要改的。"
            if language == "zh"
            else f"{holder.capitalize()} {'hold' if holder == 'you' else 'holds'} no matching "
            "tasks; nothing to change."
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


def _allowed(expected: str, language: str) -> str:
    """The validator's "'approve' or 'rework'" as 「通过、打回」; number ranges stay."""
    quoted = re.findall(r"'([^']*)'", expected)
    if not quoted:
        return expected
    if any(item not in ENUM_LABELS for item in quoted):
        return ""  # internal choice names are never listed to a person
    words = [ENUM_LABELS.get(item, (item, item))[0 if language == "zh" else 1] for item in quoted]
    return ("、" if language == "zh" else ", ").join(words)


def invalid_question(problem: str, language: str) -> str:
    """Values the action rejects, named with what is allowed; never the raw error."""
    parts: list[str] = []
    for entry in dict.fromkeys(problem.split("|")):
        field, _, allowed = entry.partition(":")
        label = field_label(field, language)
        expected = _allowed(allowed, language)
        if language == "zh":
            parts.append(f"「{label}」的值不行" + (f"(可以是 {expected})" if expected else ""))
        else:
            parts.append(
                f'the value for "{label}"' + (f" (allowed: {expected})" if expected else "")
            )
    joined = "; ".join(parts)
    if language == "zh":
        return f"这个计划还不能执行: {joined}。请改一下说法或补充后再试。"
    return f"This plan cannot run yet: {joined} is not allowed. Please adjust and try again."


def broken_plan(language: str) -> str:
    """A planned step failed an internal check; say so plainly, nothing was changed."""
    if language == "zh":
        return "这个计划里有一步我没法核对清楚, 所以没有生成卡片, 什么都没改。请换个说法再试。"
    return (
        "I could not check one step of this plan, so no card was made and nothing changed. "
        "Please rephrase and try again."
    )


def already_so(language: str) -> str:
    """Every step would leave things as they are: nothing to confirm."""
    if language == "zh":
        return "已经是这样了, 没有要改的, 所以没有生成计划。"
    return "It is already like that; there is nothing to change, so no plan was made."


def unknown_labels_question(unknown: list[str], existing: list[str], language: str) -> str:
    """A label the person named is not in the label set: say which ones are."""
    shown = existing[:8]
    if language == "zh":
        return f"标签集里没有「{'、'.join(unknown)}」。现有标签: {'、'.join(shown)}。要改哪一个?"
    return f"The label set has no {', '.join(unknown)}. It has: {', '.join(shown)}. Which one?"


FAILURE_REASONS = {
    "timeout": ("超时", "it timed out"),
    "unreadable": ("回答无法解析", "its answer could not be read"),
    "network": ("网络错误", "a network error"),
    "provider": ("模型服务没有返回可用结果", "the model service returned no usable result"),
}


def model_failed(reason: str, language: str) -> str:
    """The model call itself failed: say so with the reason; nothing was changed."""
    zh = language == "zh"
    known = FAILURE_REASONS.get(reason)
    if known is not None:
        said = known[0 if zh else 1]
    elif reason.startswith("http_"):
        said = f"HTTP {reason.removeprefix('http_')}"
    else:
        said = "调用出错" if zh else "the call failed"
    if zh:
        return f"模型调用失败 ({said}), 这句话还没处理, 什么都没改。可以稍后重试。"
    return (
        f"The model call failed ({said}), so this sentence was not handled and nothing "
        "changed. Please try again."
    )


def internal_failure(language: str) -> str:
    """An internal check failed: say it plainly without exposing the raw error."""
    if language == "zh":
        return "处理这句话时平台内部出错了, 什么都没改。请换个说法, 或稍后再试。"
    return (
        "Something went wrong inside the platform while handling this sentence; nothing "
        "changed. Please rephrase or try again later."
    )


def missing_feature(close: list[str], language: str) -> str:
    """The platform has no such feature: say so, and name close things it can do."""
    if language == "zh":
        return f"平台没有这个功能, 所以什么都没做。相近的能做的有: {'、'.join(close)}。"
    return (
        "The platform has no feature for this, so nothing was done. "
        f"Close things it can do: {', '.join(close)}."
    )


def related_question(titles: list[str], language: str) -> str:
    """The words fit several registered actions equally well: ask which one."""
    if language == "zh":
        return (
            f"我没能把这句话对上具体的操作。相关的有: {'、'.join(titles)}。"
            "你想做哪一个? 也可以换个说法。"
        )
    return (
        f"I could not match this to a specific operation. Related ones: {', '.join(titles)}. "
        "Which one did you mean? You can also rephrase."
    )


def disabled_question(name: str, language: str) -> str:
    """A disabled account cannot be given work; say so and ask who else."""
    if language == "zh":
        return f"{name} 的账号已停用, 不能接收任务。要先启用这个账号, 还是换一个人?"
    return (
        f"{name}'s account is disabled, so it cannot receive work. "
        "Enable it first, or pick someone else?"
    )


def whole_tasks_question(language: str) -> str:
    """The words did not say which tasks; never assume every task in the project."""
    if language == "zh":
        return (
            "是这个项目里的全部任务吗? 如果是请说「全部」, "
            "否则说一下是哪些任务(谁手上的、没人领的、第几个)。"
        )
    return (
        'Every task in this project? Say "all" if so; otherwise say which ones (whose, '
        "unassigned, or their numbers)."
    )


def not_found_question(language: str) -> str:
    """A step names something that does not exist: ask instead of failing."""
    if language == "zh":
        return "这一步提到的对象没找到 (可能名字不一样), 是哪一个?"
    return "Something this step names was not found (perhaps under another name); which is it?"
