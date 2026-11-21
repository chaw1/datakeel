# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Specialist definitions fail before execution when capabilities or bounds are invalid."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.settings import Settings
from datakeel.delegation.loader import agents_path, get_agent, list_agents

if TYPE_CHECKING:
    from pathlib import Path


def test_bundled_agents_expose_required_scopes() -> None:
    """Ship six specialists with explicit read-only and reversible action scopes."""
    agents = {item.name: item for item in list_agents()}
    assert set(agents) == {
        "catalog-analyst",
        "evidence-reviewer",
        "kg-standard-analyst",
        "metric-manager",
        "production-ops",
        "training-auditor",
    }
    assert {"get_lineage", "list_metrics", "impact_of"} <= set(agents["catalog-analyst"].tools)
    assert "decide_assertions" in agents["evidence-reviewer"].tools
    assert {"update_metric", "rollback_metric"} <= set(agents["metric-manager"].tools)
    assert get_agent("catalog-analyst").max_turns == 4
    assert agents_path().is_dir()
    with pytest.raises(NotFoundError, match="Unknown delegated"):
        get_agent("missing")


@pytest.mark.parametrize(
    ("name", "tools"),
    [
        (
            "production-ops",
            (
                "project_progress package_status package_acceptance annotator_workload "
                "skill_workload rework_rate annotation_consistency prelabel_confidence "
                "production_prelabel_accuracy lease_status assignees production_objects "
                "label_set_diff delegate_agent"
            ),
        ),
        (
            "training-auditor",
            (
                "list_datasets training_distribution training_leakage get_training_quality "
                "annotation_quality get_quality get_report delegate_agent"
            ),
        ),
        (
            "kg-standard-analyst",
            (
                "query_kg explain_relation query_standard_coverage list_standard_usage "
                "get_table_quality list_quality_rules list_datasets delegate_agent"
            ),
        ),
    ],
)
def test_domain_specialists_have_exact_read_only_scopes(name: str, tools: str) -> None:
    """Keep each new domain specialist bounded to its declared reads and four turns."""
    agent = get_agent(name)
    assert agent.tools == tools.split()
    assert agent.max_turns == 4


@pytest.mark.parametrize(
    ("extra", "field"),
    [
        ("tools: [invented]", "tools.0"),
        ("tools: [delete_files]", "tools.0"),
        ("tools: [list_datasets]\nmax_turns: 5", "max_turns"),
    ],
)
def test_bad_definition_reports_file_and_field(tmp_path: Path, extra: str, field: str) -> None:
    """Name exact contract locations for unknown tools, irreversible tools and excessive turns."""
    (tmp_path / "bad.yaml").write_text(f"name: test-agent\ndescription: Test\n{extra}\n")
    with pytest.raises(ValidationError, match=f"bad.yaml:{field}"):
        list_agents(tmp_path)


def test_duplicate_and_malformed_definitions_are_rejected(tmp_path: Path) -> None:
    """Reject ambiguous names and invalid YAML without allowing a partial registry."""
    with pytest.raises(ValidationError, match="no agent definitions"):
        list_agents(tmp_path)
    content = "name: same\ndescription: Test\ntools: [list_datasets]\n"
    (tmp_path / "a.yaml").write_text(content)
    (tmp_path / "b.yaml").write_text(content)
    with pytest.raises(ValidationError, match=r"b.yaml:name: duplicate"):
        list_agents(tmp_path)
    (tmp_path / "b.yaml").write_text("[")
    with pytest.raises(ValidationError, match=r"b.yaml:document"):
        list_agents(tmp_path)


def test_delegation_limits_share_validated_settings() -> None:
    """Both limits are positive and bounded at the sole application configuration boundary."""
    assert Settings().delegation_max_depth == 2
    assert Settings().delegation_max_parallel == 3
    with pytest.raises(ValueError, match="delegation_max_depth"):
        Settings(delegation_max_depth=0)
    with pytest.raises(ValueError, match="delegation_max_parallel"):
        Settings(delegation_max_parallel=0)
