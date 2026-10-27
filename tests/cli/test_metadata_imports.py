# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Local artifact commands reject malformed files and report actual catalog changes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from datakeel.catalog import metadata_service
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_queries import get_object

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.catalog.importers.airflow_rest import AirflowConnection
    from datakeel.storage.database import Database
    from tests.cli.conftest import Invoke


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json"
                },
                "nodes": {
                    "model.shop.orders": {
                        "unique_id": "model.shop.orders",
                        "resource_type": "model",
                        "name": "orders",
                        "schema": "main",
                        "relation_name": '"main"."orders"',
                        "description": "Generated order totals",
                        "columns": {"id": {"name": "id", "data_type": "INTEGER"}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_dbt_when_valid_manifest_supplied_imports_and_replays(
    invoke: Invoke, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Repeated local artifact imports retain stable identities and expose unchanged counts."""
    path = _manifest(tmp_path)
    catalog = tmp_path / "catalog.json"
    catalog.write_text('{"nodes": {}}')
    results = tmp_path / "run_results.json"
    results.write_text('{"results": []}')
    invoke(
        "import",
        "dbt",
        "--source-id",
        "shop",
        "--manifest",
        str(path),
        "--catalog",
        str(catalog),
        "--run-results",
        str(results),
        "--name",
        "Shop",
    )
    first = json.loads(capsys.readouterr().out)
    assert first["new"] >= 2
    invoke(
        "import",
        "dbt",
        "--source-id",
        "shop",
        "--manifest",
        str(path),
        "--catalog",
        str(catalog),
        "--run-results",
        str(results),
        "--name",
        "Shop",
    )
    second = json.loads(capsys.readouterr().out)
    assert second["new"] == second["changed"] == second["deleted"] == 0
    assert second["unchanged"] == first["object_count"]


def test_airflow_when_offline_export_supplied_creates_dag(
    db: Database, invoke: Invoke, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Airflow commands consume supplied JSON without constructing a remote client."""
    path = tmp_path / "airflow.json"
    path.write_text('{"dags":[{"dag_id":"daily_orders","owners":["Data team"]}]}')
    invoke("import", "airflow", "--source-id", "scheduler", "--file", str(path))
    assert json.loads(capsys.readouterr().out)["new"] >= 1
    assert get_object(db, "scheduler/dag/daily_orders").name == "daily_orders"


@pytest.mark.parametrize("content", ["[", "[]", "null", '"text"'])
def test_import_when_file_not_json_object_exits_with_actionable_error(
    invoke: Invoke, tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    """Invalid decoding never becomes a traceback or a partial catalog import."""
    path = tmp_path / "invalid.json"
    path.write_text(content)
    with pytest.raises(SystemExit, match="1"):
        invoke("import", "airflow", "--source-id", "scheduler", "--file", str(path))
    assert "Import failed:" in capsys.readouterr().out


def test_import_when_file_missing_exits_with_file_error(
    invoke: Invoke, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing local artifacts identify the filesystem failure for the operator."""
    with pytest.raises(SystemExit, match="1"):
        invoke("import", "dbt", "--source-id", "shop", "--manifest", str(tmp_path / "absent.json"))
    assert "Import failed:" in capsys.readouterr().out


def test_airflow_when_api_selected_reads_configured_scheduler(
    db: Database,
    invoke: Invoke,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--api uses DATAKEEL_AIRFLOW_* settings and the selected DAG subset."""
    monkeypatch.setenv("DATAKEEL_AIRFLOW_URL", "https://scheduler.example")
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fetch(
        connection: AirflowConnection, dag_ids: tuple[str, ...], _transport: object
    ) -> JsonDocument:
        calls.append((connection.base_url, dag_ids))
        return JsonDocument({"dags": [{"dag_id": "daily_orders", "owners": ["Data team"]}]})

    monkeypatch.setattr(metadata_service, "fetch_airflow_export", fetch)
    invoke("import", "airflow", "--source-id", "scheduler", "--api", "--dag", "daily_orders")
    assert json.loads(capsys.readouterr().out)["new"] >= 1
    assert calls == [("https://scheduler.example", ("daily_orders",))]
    assert get_object(db, "scheduler/dag/daily_orders").name == "daily_orders"


def test_airflow_when_api_selected_without_url_exits_with_configuration_error(
    invoke: Invoke, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A live import never guesses a scheduler address."""
    monkeypatch.delenv("DATAKEEL_AIRFLOW_URL", raising=False)
    with pytest.raises(SystemExit, match="1"):
        invoke("import", "airflow", "--source-id", "scheduler", "--api")
    assert "DATAKEEL_AIRFLOW_URL" in capsys.readouterr().out


def test_airflow_when_file_and_api_both_given_rejects_arguments(invoke: Invoke) -> None:
    """Offline and live origins are mutually exclusive."""
    with pytest.raises(SystemExit, match="2"):
        invoke("import", "airflow", "--source-id", "s", "--api", "--file", "export.json")
