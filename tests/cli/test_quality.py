# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""YAML CLI preparation preserves approval and shares persisted monitoring reads."""

import json
from pathlib import Path

import pytest
import yaml

from datakeel.cli import parser
from datakeel.cli.quality import dispatch, prepare_import
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.dq_reads import read_rules
from datakeel.worker.runner import run_worker
from tests.dq_support import generated_rule, save_rule


def test_quality_yaml_import_prepares_without_implicitly_approving(
    db: Database,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both initial imports and revisions produce frozen review plans without mutations."""
    rule = generated_rule(db, tmp_path)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "rules": [rule.model_dump(mode="json")]}))
    arguments = parser().parse_args(["quality", "validate", str(path)])
    dispatch(db, arguments)
    assert json.loads(capsys.readouterr().out)["rules"][0]["id"] == rule.id
    dispatch(db, parser().parse_args(["quality", "import", str(path)]))
    assert json.loads(capsys.readouterr().out)["plans"][0]["action_type"] == "create_quality_rule"
    assert not read_rules(db)
    save_rule(db, rule)
    plan = prepare_import(db, path)[0]
    assert plan.action_type == "update_quality_rule"
    assert plan.canonical_params["expected_revision"] == 1
    assert plan.requires_approval
    assert read_rules(db)[0].revision == 1


def test_quality_cli_run_list_and_report_share_worker_facts(
    db: Database,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command enqueues a read-only task and later reports its measured failure."""
    rule = generated_rule(db, tmp_path)
    save_rule(db, rule)
    dispatch(db, parser().parse_args(["quality", "run", rule.id]))
    queued = JsonDocument.model_validate_json(capsys.readouterr().out)
    assert queued.root["task_id"]
    run_worker(db, once=True)
    dispatch(db, parser().parse_args(["quality", "list"]))
    assert json.loads(capsys.readouterr().out)["items"][0]["latest_result"]["status"] == "failed"
    dispatch(
        db,
        parser().parse_args(
            ["quality", "report", "--source-id", "orders-test", "--table", "orders"]
        ),
    )
    assert json.loads(capsys.readouterr().out)["summary"]["failed"] == 1
