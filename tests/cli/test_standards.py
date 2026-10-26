# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Readable CLI inspection and explicit standards approval over generated local data."""

from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter

from datakeel.cli import parser
from datakeel.cli.standards import dispatch
from datakeel.standards.loader import dump_contract
from datakeel.storage.database import Database
from datakeel.storage.standard_store import get_contract
from tests.standards_support import install_standards, standard_contract


def _command(
    db: Database, arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> dict[str, JsonValue] | list[JsonValue]:
    dispatch(db, parser().parse_args(["standards", *arguments]))
    value = TypeAdapter(JsonValue).validate_json(capsys.readouterr().out)
    assert isinstance(value, dict | list)
    return value


def test_import_prepares_until_explicit_review_and_execution(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default import cannot silently approve its own plan; two explicit commands complete it."""
    path = tmp_path / "standards.yaml"
    path.write_text(dump_contract(standard_contract()))
    result = _command(db, ["import", str(path)], capsys)
    assert isinstance(result, dict)
    assert not get_contract(db).standards
    identifier = str(result["id"])
    _command(db, ["approve", identifier], capsys)
    executed = _command(db, ["execute", identifier], capsys)
    assert isinstance(executed, dict)
    assert executed["status"] == "SUCCEEDED"
    assert len(get_contract(db).standards) == 4


def test_cli_inspects_searches_exports_and_reports_without_mutating(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Lists, suggestions, history, JSON Schema and reports retain the same read-only contract."""
    install_standards(db, tmp_path)
    assert len(_command(db, ["list", "--search", "客户", "--status", "active"], capsys)) == 2
    assert len(_command(db, ["code-lists", "--search", "Active"], capsys)) == 1
    for command in ("history", "schema", "check", "coverage"):
        assert isinstance(_command(db, [command], capsys), dict)
    for command in ("profiles", "suggestions"):
        assert len(_command(db, [command], capsys)) == 5
    assert _command(db, ["mappings"], capsys) == []
    output = tmp_path / "export.yaml"
    dispatch(db, parser().parse_args(["standards", "export", "--output", str(output)]))
    assert "name_zh:" in output.read_text()
    dispatch(db, parser().parse_args(["standards", "export"]))
    assert "name_zh:" in capsys.readouterr().out


def test_explicit_cli_confirmation_and_rollback_are_controlled(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An explicit approval flag signs only the reviewed generated change and preserves rollback."""
    install_standards(db, tmp_path)
    result = _command(
        db, ["confirm", "generated/main/customers/cust_id", "customer_id", "--approve"], capsys
    )
    assert isinstance(result, dict)
    assert result["status"] == "SUCCEEDED"
    assert _command(db, ["mappings"], capsys)
    result = _command(db, ["rollback", "1", "--approve"], capsys)
    assert isinstance(result, dict)
    assert result["status"] == "SUCCEEDED"
    assert _command(db, ["mappings"], capsys) == []


def test_cli_dry_run_and_rejection_leave_contract_unchanged(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dry-run plan can be rejected without writing a standards revision."""
    path = tmp_path / "standards.yaml"
    path.write_text(dump_contract(standard_contract()))
    plan = _command(db, ["import", str(path), "--dry-run", "--approve"], capsys)
    assert isinstance(plan, dict)
    _command(db, ["approve", str(plan["id"]), "--reject"], capsys)
    assert not get_contract(db).standards


def test_cli_demo_seeds_generated_approved_fixtures_and_reports(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The explicit demo command produces both clean and intentionally nonconforming columns."""
    report = _command(db, ["demo", "--directory", str(tmp_path / "demo")], capsys)
    assert isinstance(report, dict)
    coverage = report["coverage"]
    assert isinstance(coverage, dict)
    assert coverage["violation_top"]
