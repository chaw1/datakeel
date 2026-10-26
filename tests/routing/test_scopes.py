# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Negation, restricted steps and active requests retain their own workflow scope."""

import pytest

from tests.routing.intent_helpers import resolve_route


def test_negated_named_workflow_when_high_score_has_no_route() -> None:
    """Negation defeats a complete entity, operation and workflow-name conjunction."""
    assert resolve_route("Never run a dataset health check.").workflow_id is None
    assert resolve_route("Run a dataset health check.").workflow_id == "dataset-health"


@pytest.mark.parametrize(
    "message",
    [
        "Never run a dataset health check.",
        "请勿运行数据集体检。",
        "先不做数据集健康检查。",
        "Never tidy up low-quality files.",
        "I want to read the dataset health check result, not run it.",
        "Run only the preprocessing stage of the dataset health check.",
        "Only quarantine and clean up the low-quality files; keep all originals.",
        "低质量样本清理只做隔离这一步。",
        "请给数据集做体检, 但仅返回已有质量分。",
        "Run only the measure-column update of the metric definition change.",
        "I am not asking you to run dataset health check.",
        "数据集体检暂不启动。",
        "Please don't perform a complete health check for this dataset.",
        "暂缓执行指标口径变更。",
        "不必清理低质量样本。",
        "取消指标口径变更, 保留原来的问数结果。",
        "The low-quality sample cleanup was cancelled yesterday.",
        "We already completed the dataset health check.",
        "Just show the current metric definition change status.",
        "Please run the dataset health check's report-reading step only.",
        "Only compare the old and new metric answers; leave the measure column alone.",
        "整理低质样本但保留所有原始文件。",
    ],
)
def test_limited_or_inactive_workflow_when_mentioned_does_not_route(message: str) -> None:
    """Even a direct high-score match cannot widen a denial or a single-step request."""
    assert resolve_route(message).workflow_id is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "I canceled low-quality sample cleanup. Run the dataset health check.",
            "dataset-health",
        ),
        (
            (
                "Regarding the metric definition change, I only need the current value. "
                "Please perform the dataset health check."
            ),
            "dataset-health",
        ),
        (
            "Low-quality files need cleanup eventually; for now run the dataset health check.",
            "dataset-health",
        ),
        ("请先看低质样本清理的记录, 再给数据集做全面体检。", "dataset-health"),
        (
            "Do not clean up low-quality files; run a dataset health check instead.",
            "dataset-health",
        ),
        ("不要清理低质样本, 给数据集做体检。", "dataset-health"),
        (
            "For this dataset, perform a complete health assessment.",
            "dataset-health",
        ),
        (
            "These defective files should be purged, then quality rechecked.",
            "low-quality-cleanup",
        ),
        ("Culling bad samples after review, please.", "low-quality-cleanup"),
        (
            "Recompute the answer after revising the metric calculation.",
            "metric-change",
        ),
        ("重新问数并比较结果, 度量字段换成新的。", "metric-change"),
    ],
)
def test_current_workflow_when_other_topic_is_inactive_selects_current_request(
    message: str, expected: str
) -> None:
    """An earlier noun mention cannot override the current requested operation."""
    assert resolve_route(message).workflow_id == expected
