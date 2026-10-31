# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The planner's registry lines: every entry once, no phrase that only repeats its name."""

from datakeel.intents.model_parse import _catalog_lines
from datakeel.intents.rules import full_registry


def _lines() -> dict[str, str]:
    text = _catalog_lines(full_registry())
    return {line.split("(", 1)[0]: line for line in text.splitlines()}


def test_registry_lines_never_spell_a_name_out_twice() -> None:
    """A phrase equal to the name with spaces is left out; a phrase that adds words stays."""
    lines = _lines()
    assert lines["action assign_tasks"].endswith("): 派单")
    assert lines["action upgrade_project_template"].endswith("): 升级项目模板版本")
    assert lines["read assignees"].endswith("): 可派的人")
    assert lines["action configure_project"].endswith(": 配置团队档 / configure team settings")
    for key, line in lines.items():
        spelled = key.split(" ", 1)[1].replace("_", " ")
        assert not line.casefold().endswith(f"/ {spelled}"), line


def test_server_written_handovers_are_not_offered_to_the_model() -> None:
    """Rework handovers are recomputed when a plan is prepared, so the model never sees them."""
    assignment = _lines()["action assign_tasks"]
    assert "transfers" not in assignment
    assert "max_active_tasks" in assignment
