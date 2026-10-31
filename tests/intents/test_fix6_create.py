# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX6: what a step registers is created, not looked up, and its name is not asked again."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.intents.named_kinds import named_kinds, named_version
from tests.intents.fix3_support import SOUTH, planned, steps, two_projects

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
