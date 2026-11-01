# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""What a step registers is created, not looked up, and its name is not asked again."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.intents.catalog import build_catalog
from datakeel.intents.edits import latest_label_set
from datakeel.intents.named_kinds import named_kinds, named_version, said_version
from tests.intents.planning_support import SOUTH, planned, steps, two_projects
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_a_model_registered_earlier_in_the_plan_is_used_by_name_or_as_it(db: Database) -> None:
    """A model registered earlier in the plan is used by name or as it."""
    two_projects(db)
    for said in ("夜视框选", "它"):
        result = planned(
            db,
            "登记一个叫夜视框选的模型, 然后用它预标注南区车道",
            [
                steps(
                    ("register_model", {"model": {"name": "夜视框选", "version": "1"}}),
                    ("run_prelabel", {"project_id": SOUTH, "model_id": said}),
                )
            ],
            PageContext(),
        )
        assert result.kind == "plan", result.text
        assert result.chain is not None
        model = result.chain.steps[0].params["model"]
        assert isinstance(model, dict)
        assert result.chain.steps[1].params["model_id"] == model["id"]


def test_what_a_new_models_name_says_is_never_asked(db: Database) -> None:
    """What a new models name says is never asked."""
    two_projects(db)
    result = planned(
        db,
        "Register the model rain-poly-v2",
        [steps(("register_model", {"model": {"name": "rain-poly-v2"}}))],
        PageContext(),
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    model = result.chain.steps[0].params["model"]
    assert isinstance(model, dict)
    assert model["version"] == "2"
    assert model["capabilities"] == ["polygon"]


def test_a_new_skills_type_comes_from_its_name(db: Database) -> None:
    """A new skills type comes from its name."""
    two_projects(db)
    result = planned(
        db,
        "新建技能「路口车辆框选」, 领域是交通",
        [
            steps(
                ("manage_skills", {"operation": "create", "name": "路口车辆框选", "domain": "交通"})
            )
        ],
        PageContext(),
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["annotation_type"] == "box"


def test_names_say_only_what_they_say_outright() -> None:
    """Names say only what they say outright."""
    assert named_kinds("路口车辆框选") == ["box"]
    assert named_kinds("lane-seg-large") == ["polygon"]
    assert named_kinds("南区车道") == []
    assert named_version("rain-poly-v2.1") == "2.1"
    assert named_version("rainpoly") is None


def test_a_reference_inside_a_list_is_the_object_made_earlier(db: Database) -> None:
    """A "$ref: s1.skill_id" written in a list of skills is the skill the first step makes."""
    two_projects(db)
    answer = {
        "kind": "plan",
        "steps": [
            {
                "id": "s1",
                "action": "manage_skills",
                "params": {
                    "operation": "create",
                    "name": "夜间车框",
                    "annotation_type": "box",
                    "domain": "交通",
                },
            },
            {
                "id": "s2",
                "action": "manage_users",
                "params": {
                    "operation": "update",
                    "user_id": "小王",
                    "add_skill_ids": ["$ref: s1.skill_id"],
                },
            },
        ],
    }
    result = planned(
        db, "新建技能「夜间车框」, 框标注, 交通领域, 再给小王加上", [answer], PageContext()
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    made = result.chain.steps[0].params["skill_id"]
    assert made in (result.chain.steps[1].params.get("skill_ids") or [])
    shown = " ".join(detail.value for step in result.chain.steps for detail in step.details)
    assert "$ref" not in shown


def test_the_persons_words_win_over_the_models_identity(db: Database) -> None:
    """The model wrote 小赵's id but the person said 小李: 小李 is the one."""
    _, _, tasks = two_projects(db)
    answer = {
        "kind": "plan",
        "steps": [
            {
                "id": "s1",
                "action": "assign_tasks",
                "params": {"task_ids": tasks[4:5], "actor": "zhao"},
                "said": {"actor": "小李"},
            }
        ],
    }
    result = planned(db, "南区车道第五条找小李来标", [answer], PageContext())
    assert result.chain is not None, result.text
    assert result.chain.steps[0].params["actor"] == "li"


def test_template_roles_are_found_by_their_chinese_names(db: Database) -> None:
    """「质检员」 is the reviewer role, never "no role called 质检员"."""
    two_projects(db)
    bind = {"operation": "bind_role", "user_id": "小王", "role_id": "质检员", "project_id": SOUTH}
    result = planned(db, "让小王在南区车道当质检员", [steps(("manage_users", bind))], PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["role_id"] == "reviewer"


def test_a_skill_requirement_said_in_words_is_the_registered_type(db: Database) -> None:
    """A skill requirement's type said in words is the registered type, and the card names it."""
    two_projects(db)
    need = {"annotation_type": "分类标注", "domain": "交通", "min_level": 2}
    result = planned(
        db,
        "把南区车道改成按技能派单, 要分类标注、交通领域、2 级以上",
        [
            steps(
                (
                    "configure_project",
                    {"project_id": SOUTH, "dispatch_strategy": "skill", "skill_requirement": need},
                )
            )
        ],
        PageContext(),
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["skill_requirement"] == {
        **need,
        "annotation_type": "classification",
    }
    assert "最低等级" in result.text + str(result.model_dump()), result.text


def test_a_version_named_by_its_shown_label_is_found(db: Database) -> None:
    """The planner is shown "<dataset> · v1"; that label copied back finds the version."""
    two_projects(db)
    catalog = build_catalog(db)
    versions = catalog.of("version")
    assert versions
    for entry in versions:
        shown = entry.label.split(" (")[0]
        assert catalog.match("version", shown, entry.parent) == [entry]


def test_action_names_written_as_scopes_grant_those_actions(db: Database) -> None:
    """Action names the model writes under scopes stand for those actions' scopes."""
    two_projects(db)
    result = planned(
        db,
        "Define a role called Night Checker that can review tasks and accept packages",
        [
            steps(
                (
                    "define_role",
                    {"name": "Night Checker", "scopes": ["review_task", "accept_package"]},
                )
            )
        ],
        PageContext(),
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    scopes = result.chain.steps[0].params["scopes"]
    assert isinstance(scopes, list)
    assert {"production:accept", "production:review"} <= set(scopes)


def test_an_account_made_earlier_can_be_given_a_skill_by_reference(db: Database) -> None:
    """A new account referred to as {"$ref": ...} in the next step does not break planning."""
    two_projects(db)
    ServiceRunner(db)(
        "manage_skills",
        {
            "operation": "create",
            "skill_id": "lane-box",
            "name": "车道框选",
            "domain": "交通",
            "annotation_type": "box",
        },
        "boss",
    )
    try:
        result = planned(
            db,
            "New account lina for 李娜, and give her the 车道框选 skill",
            [
                steps(
                    (
                        "manage_users",
                        {"operation": "create", "user_id": "lina", "display_name": "李娜"},
                    ),
                    (
                        "manage_users",
                        {
                            "operation": "update",
                            "user_id": {"$ref": "s1.user_id"},
                            "skill_ids": ["车道框选"],
                        },
                    ),
                )
            ],
            PageContext(),
        )
    except TypeError as error:  # a reference must never reach a lookup by name
        raise AssertionError(str(error)) from error
    assert result.kind == "plan", result.text


def test_a_label_set_version_said_in_words_is_that_version(db: Database) -> None:
    """A label set's "第 2 版" is that version, never quietly the newest published one."""
    _, south, _ = two_projects(db)
    current = latest_label_set(db, south.label_set_id)
    assert current is not None
    labels = [{"id": label.id, "name": label.name} for label in current.labels]
    draft = {
        "label_set_id": south.label_set_id,
        "previous_version": current.version,
        "name": current.name,
    }
    ServiceRunner(db)(
        "create_label_set", {**draft, "labels": [*labels, {"id": "cone", "name": "锥桶"}]}, "boss"
    )
    dataset = build_catalog(db).get("dataset", south.dataset_id)
    assert dataset is not None
    step = {
        "id": "s1",
        "action": "create_project",
        "params": {
            "name": "车道复查",
            "dataset_id": dataset.id,
            "label_set_id": south.label_set_id,
        },
        "said": {"label_set_id": f"{current.name}第 2 版", "dataset_id": dataset.label},
    }
    result = planned(
        db,
        f"拿{current.name}第 2 版给{dataset.label}开个新项目, 叫「车道复查」",
        [{"kind": "plan", "steps": [step]}],
        PageContext(),
    )
    assert result.kind != "plan", result.text
    assert "第 2 版" in result.text, result.text
    assert said_version("集装箱类型第 2 版") == 2
    assert said_version("version 3 of the labels") == 3
    assert said_version("集装箱类型 v1") is None
