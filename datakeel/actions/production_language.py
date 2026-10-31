# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bilingual vocabulary for discoverable production actions, without natural-language execution."""

PRODUCTION_LANGUAGE: dict[str, tuple[str, str, str, str]] = {
    "create_label_set": (
        "创建标签集",
        "create label set",
        "创建动物标签集第一版",
        "Create an animal label set v1",
    ),
    "publish_label_set": (
        "发布标签集",
        "publish label set",
        "发布已检查的标签集第二版",
        "Publish reviewed labels v2",
    ),
    "create_project": (
        "创建生产项目",
        "create production project",
        "用这个版本建个人标注项目",
        "Create a personal annotation project from this version",
    ),
    "split_packages": (
        "切分任务包",
        "split packages",
        "每一百张图片切成一包",
        "Split images into packages of 100",
    ),
    "assign_tasks": (
        "派单",
        "assign tasks",
        "把这些任务派给标注员",
        "Assign these tasks to the annotator",
    ),
    "claim_task": (
        "领取任务",
        "claim task",
        "领取下一条待标任务",
        "Claim the next annotation task",
    ),
    "release_task": (
        "放弃任务",
        "release task",
        "放弃我领取的这条任务",
        "Release my current assignment",
    ),
    "save_revision": (
        "保存标注修订",
        "save revision",
        "基于上一版保存这个框",
        "Save this box from the previous revision",
    ),
    "submit_task": (
        "提交任务",
        "submit task",
        "提交当前标注",
        "Submit the current annotation",
    ),
    "review_task": (
        "审核任务",
        "review task",
        "退回任务并记录漏标问题",
        "Return the task with a missing box issue",
    ),
    "reopen_task": (
        "重开任务",
        "reopen task",
        "定稿前重开这条任务",
        "Reopen this task before finalization",
    ),
    "upgrade_project": (
        "升级工作流档位",
        "upgrade workflow tier",
        "把个人项目升为小组档",
        "Upgrade the personal project to group workflow",
    ),
    "heartbeat": (
        "续租",
        "renew lease",
        "我还在标这条, 续租",
        "Keep my lease on this task alive",
    ),
    "revoke_assignment": (
        "收回指派",
        "revoke assignment",
        "把小王手里没动的任务收回到待标",
        "Take the untouched task back from its holder",
    ),
    "configure_project": (
        "配置团队档",
        "configure team settings",
        "租约改成十五分钟, 按技能派单, 每人最多五条",
        "Use 15-minute leases, skill dispatch and at most five tasks each",
    ),
    "accept_package": (
        "抽检验收任务包",
        "accept package by sampling",
        "按 AQL 2.5 抽检这个任务包并验收",
        "Inspect this package at AQL 2.5 and accept it",
    ),
    "upgrade_project_template": (
        "升级项目模板版本",
        "upgrade project template",
        "把这个项目升级到模板和标签集的最新版",
        "Upgrade this project to the newest template and label versions",
    ),
    "register_model": (
        "登记预标注模型",
        "register prelabel model",
        "登记我的外部预测模型",
        "Register the provenance of my external predictions",
    ),
    "update_model": (
        "修改预标注模型",
        "update prelabel model",
        "修改假模型的版本",
        "Update the fake model version",
    ),
    "import_predictions": (
        "导入预测",
        "import predictions",
        "按标签映射导入这些COCO预测",
        "Import these COCO predictions with label mapping",
    ),
    "run_prelabel": (
        "运行假模型预标注",
        "run fake prelabel",
        "对这个包运行假模型",
        "Run the fake model on this package",
    ),
    "finalize_project": (
        "定稿项目",
        "finalize project",
        "把全部通过的修订定稿进新版本",
        "Finalize all approved revisions into a new dataset version",
    ),
    "manage_users": (
        "管理用户和团队",
        "manage users and teams",
        "登记标注员并绑定项目角色",
        "Register an annotator and bind a project role",
    ),
    "manage_skills": (
        "管理技能",
        "manage skills",
        "新增图片框标注技能",
        "Add an image box annotation skill",
    ),
    "define_role": (
        "定义角色",
        "define role",
        "加一个外包组长角色, 能派单和看返工率, 不能定稿",
        "Add a contractor lead who can assign and view rework rates but cannot finalize",
    ),
    "update_role": (
        "修改角色",
        "update role",
        "把这个角色的权限收窄为派单",
        "Narrow this role to task assignment",
    ),
}


def action_language(name: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return independently editable phrases and concrete examples for both languages."""
    value = PRODUCTION_LANGUAGE.get(name)
    if value is None:
        return {}, {}
    zh, en, example_zh, example_en = value
    return {"zh": [zh], "en": [en]}, {"zh": [example_zh], "en": [example_en]}
