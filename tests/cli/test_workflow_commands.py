# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose workflow contract inspection and identical validation errors through the CLI."""

from pathlib import Path

import pytest

from datakeel.workflows.loader import workflows_path
from tests.cli.conftest import Invoke
from tests.workflows.test_definitions import definition, output, tool, write_definition


def test_workflow_list_includes_three_builtins(
    invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """List contracts without creating a workflow run."""
    invoke("workflow", "list")
    result = capsys.readouterr().out
    assert all(
        name in result for name in ("dataset-health", "metric-change", "low-quality-cleanup")
    )


def test_workflow_validate_accepts_bundled_schema(
    invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """The shipped health workflow validates through its user-facing command."""
    invoke("workflow", "validate", str(workflows_path() / "dataset-health.yaml"))
    assert "Workflow definition is valid." in capsys.readouterr().out


def test_workflow_validate_reports_file_and_step(
    invoke: Invoke, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Validation exits unsuccessfully and preserves the domain error location."""
    path = write_definition(tmp_path, definition([tool("not_registered"), output()]))
    with pytest.raises(SystemExit) as failure:
        invoke("workflow", "validate", str(path))
    assert failure.value.code == 1
    assert "workflow.yaml:steps[first]: unknown tool: not_registered" in capsys.readouterr().out
