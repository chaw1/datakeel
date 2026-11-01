# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""What a plan lacks, in Chinese and English, with what to do first."""

REASONS: dict[str, tuple[str, str]] = {
    "finalized": (
        "「{name}」已经定稿, 不能再改; 要接着做得新建一个项目",
        '"{name}" is finalized and cannot change; start a new project to go on',
    ),
    "not_approved": (
        "「{name}」还有 {count} 条任务没通过审核, 现在不能定稿; 可以先把这些任务审完",
        (
            '"{name}" still has {count} tasks not approved, so it cannot be finalized yet; '
            "review them first"
        ),
    ),
    "not_accepted": (
        "「{name}」还有 {count} 个任务包没验收, 团队档要每个包都验收后才能定稿; 可以先验收这些包",
        (
            '"{name}" has {count} packages not accepted yet; a team project finalizes only after '
            "every package is accepted, so accept them first"
        ),
    ),
    "not_team": (
        "只有团队档项目才按包验收, 「{name}」不是团队档",
        'only team projects accept work package by package, and "{name}" is not one',
    ),
    "package_not_approved": (
        "这个任务包里还有 {count} 条任务没通过审核, 现在不能验收; 可以先把它们审完",
        (
            "{count} tasks in that package are not approved yet, so it cannot be accepted; "
            "review them first"
        ),
    ),
    "accepted": (
        "这个任务包已经验收通过了, 现在的状态就是已验收, 不用再验收",
        "That package is already accepted; its state is accepted, so nothing to do",
    ),
    "not_held": (
        "其中 {count} 条任务现在不在你手上, 只有领着任务的人才能保存或提交; 可以先领取或派给你",
        (
            "{count} of those tasks are not in your hands, and only the person holding a task can "
            "save or hand it in; claim it or have it assigned to you first"
        ),
    ),
    "not_saved": (
        (
            "其中 {count} 条任务没有可提交的标注 (还没保存过, 或已经提交了), 现在不能提交; "
            "先标注并保存"
        ),
        (
            "{count} of those tasks have nothing to hand in (nothing saved yet, or already handed "
            "in); annotate and save first"
        ),
    ),
    "not_releasable": (
        "其中 {count} 条任务不在进行中 (已经提交、通过或还没开始), 不能放弃",
        (
            "{count} of those tasks are not in progress (handed in, approved or not started), so "
            "they cannot be given up"
        ),
    ),
    "split": (
        "「{name}」已经切过包了, 不能再切",
        '"{name}" is already split into packages and cannot be split again',
    ),
    "not_revocable": (
        "其中 {count} 条任务已经提交或通过了, 不能收回; 要重做可以先重新打开",
        (
            "{count} of those tasks are already submitted or approved and cannot be taken back; "
            "reopen them instead"
        ),
    ),
    "not_assignable": (
        "其中 {count} 条任务当前不能派单 (不在待派状态, 或已经有人持有); 可以先收回或重新打开",
        (
            "{count} of those tasks cannot be dispatched now (not waiting for dispatch, or "
            "already held); take them back or reopen them first"
        ),
    ),
    "no_lease": (
        "「{name}」是小组档, 领到的任务不限时, 没有领取时限要续",
        '"{name}" is a group project; claimed tasks are not timed, so there is no lease to renew',
    ),
    "nothing_free": (
        "「{name}」里现在没有可领的任务 (都已经有人在做, 或者已经交了)",
        'There is no task free to claim in "{name}" now (all are taken or handed in)',
    ),
    "nothing_free_package": (
        "这个任务包里现在没有可领的任务 (都已经有人在做, 或者已经交了)",
        "There is no task free to claim in that package now (all are taken or handed in)",
    ),
    "above_limit": (
        "这个项目每人同时最多 {limit} 条, 单次派单只能调低这个上限, 不能调到 {asked}",
        (
            "This project allows {limit} open tasks per person; one dispatch may only lower "
            "that, not raise it to {asked}"
        ),
    ),
    "over_limit": (
        (
            "{person}手上已经有 {load} 条在做, 这个项目每人同时最多 {limit} 条, 再增加 {adding} 条"
            "会超; 可以先收回或完成一些, 或者换一个人"
        ),
        (
            "{person} already holds {load} open tasks and this project allows {limit} per "
            "person, so {adding} more would go over; finish or take some back first, or use "
            "someone else"
        ),
    ),
    "assign_only": (
        "「{name}」只能由负责人派单, 不能自己领; 请负责人把任务派给你",
        '"{name}" uses manager assignment, not self-claim; ask a manager to assign a task to you',
    ),
    "own_work": (
        (
            "其中 {count} 条任务{person}标过 (包括返工前、改派前的标注和由他触发的直通), "
            "团队档里标过的人不能审; 换一个审核人"
        ),
        (
            "{person} annotated {count} of those tasks (counting earlier rounds, handovers and "
            "pass-throughs they triggered), and in a team project nobody reviews their own work; "
            "choose another reviewer"
        ),
    ),
    "up_to_date": (
        "「{name}」已经在用最新的模板和已发布的标签集版本, 没有可升级的",
        (
            '"{name}" already uses the newest template and published label-set versions; there '
            "is nothing to upgrade"
        ),
    ),
}
