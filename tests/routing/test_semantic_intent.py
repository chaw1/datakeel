# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent vocabulary composition, scope, and read-only intent regression checks."""

import pytest
from pydantic import ValidationError

from datakeel.core.routing_models import RouteCandidate
from datakeel.routing.intent import classify_offline, keyword_route
from datakeel.workflows.loader import list_workflows
from datakeel.workflows.models import WorkflowTriggers
from tests.routing.intent_helpers import resolve_route


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("开展训练数据集健康检查, 并汇总本次处理。", "dataset-health"),
        ("Could you conduct a checkup for our validation datasets?", "dataset-health"),
        ("请清理这些低质量文件, 完成后复查。", "low-quality-cleanup"),
        ("Please clean up poor quality files after my review.", "low-quality-cleanup"),
        ("把度量列改成折扣金额, 并比较两次答案。", "metric-change"),
        ("Update the measure column, then ask again.", "metric-change"),
        ("调整度量字段后重问收入问题。", "metric-change"),
        ("Replace the measure column and compare the resulting answers.", "metric-change"),
        ("运行数据集体检, 之后查看质量报告。", "dataset-health"),
        ("Please run a dataset health check, then show its quality report.", "dataset-health"),
    ],
)
def test_composed_intent_when_synonyms_and_word_order_vary_routes(
    message: str, expected: str
) -> None:
    """Domain, action and follow-up concepts compose beyond the frozen corpora."""
    result = keyword_route(message, list_workflows())
    assert (result.workflow_id, result.branch) == (expected, "keyword")


@pytest.mark.parametrize(
    "message",
    [
        "Please delete the selected duplicate thumbnails.",
        "只隔离当前筛选的低质量文件。",
        "更改度量字段的释义并重新问数。",
        "把度量列的负责人改为分析师, 然后再回答。",
        "Change the measure column description and compare the answers.",
        "Switch the measure column owner and ask again.",
        "更新度量字段文档, 不更改业务口径。",
        "How should we run dataset health checks?",
        "请介绍低质量样本清理的步骤。",
        "低质量样本清理需要哪些权限?",
        "What permissions does low-quality sample cleanup use?",
        "为什么昨天的数据集体检没有运行成功?",
        "请你帮我查看运行数据集体检生成的质量报告。",
        "Could you please list files from low-quality sample cleanup?",
        "We need to show historical records of low-quality sample cleanup.",
        "帮我查询上次执行指标口径变更的记录。",
        "Run a checkup for the dataset_archive.",
        "Exchange the measure column and compare answers.",
    ],
)
def test_composed_intent_when_single_step_or_information_only_abstains(message: str) -> None:
    """Informational workflow mentions and metadata edits never add workflow actions."""
    result = resolve_route(message)
    assert (result.workflow_id, result.branch) == (None, "free_agent")


@pytest.mark.parametrize(
    ("message", "score"),
    [
        ("inspect records", 1),
        ("audit entries", 1),
        ("inspect audit records entries", 1),
        ("inspect", 0.5),
        ("auditor records", 0.5),
    ],
)
def test_synonym_group_when_any_alternative_matches_counts_once(message: str, score: float) -> None:
    """Alternatives count once; incomplete conjunctions retain a fractional candidate score."""
    workflow = list_workflows()[0].model_copy(
        update={"triggers": WorkflowTriggers(keywords=[["inspect|audit", "records|entries"]])}
    )
    result = keyword_route(message, [workflow])
    assert result.candidates[0].score == score


def test_classifier_when_synonyms_occur_uses_earliest_actual_position() -> None:
    """The classifier applies the same literals and word boundaries as keyword routing."""
    workflows = [
        workflow.model_copy(
            update={
                "triggers": WorkflowTriggers(keywords=[["shared"]], classification_keywords=[terms])
            }
        )
        for workflow, terms in zip(list_workflows()[:2], ["late|early", "middle"], strict=True)
    ]
    candidates = [RouteCandidate(workflow_id=workflow.id, score=1) for workflow in workflows]
    assert classify_offline("early middle late", candidates, workflows) == workflows[0].id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("keywords", [[]]),
        ("keywords", [[""]]),
        ("keywords", [["data| "]]),
        ("keywords", [["|data"]]),
        ("excluded_groups", [[]]),
        ("classification_groups", [[]]),
        ("classification_groups", [["run||check"]]),
        ("verification_keywords", ["|anchor"]),
        ("excluded_groups", [["read||report"]]),
        ("excluded_keywords", [" "]),
        ("excluded_prefixes", ["view|"]),
        ("classification_keywords", ["|classify"]),
    ],
)
def test_trigger_schema_when_empty_group_or_alternative_rejects(
    field: str, value: list[str] | list[list[str]]
) -> None:
    """An empty literal cannot silently match every request or classification candidate."""
    with pytest.raises(ValidationError, match="must not be empty"):
        WorkflowTriggers.model_validate({"keywords": [["valid"]], field: value})


def test_excluded_group_when_only_one_concept_matches_does_not_veto() -> None:
    """A query/history conjunction must not become an unconditional history exclusion."""
    workflow = list_workflows()[0].model_copy(
        update={
            "triggers": WorkflowTriggers(
                keywords=[["process"]], excluded_groups=[["inspect|read", "history|log"]]
            )
        }
    )
    assert keyword_route("process the history", [workflow]).workflow_id == workflow.id
    assert keyword_route("inspect the process log", [workflow]).workflow_id is None


@pytest.mark.parametrize(
    "prefix", ["请", "请 ", "请\n", "请\n帮我  ", "麻烦你  帮我\t", "could you\nplease "]
)
def test_read_prefix_when_courtesy_contains_whitespace_still_abstains(prefix: str) -> None:
    """Courtesy removal preserves the whitespace normalization contract in both languages."""
    workflow = list_workflows()[0].model_copy(
        update={"triggers": WorkflowTriggers(keywords=[["process"]], excluded_prefixes=["查看"])}
    )
    assert keyword_route(f"{prefix}查看 process", [workflow]).workflow_id is None
