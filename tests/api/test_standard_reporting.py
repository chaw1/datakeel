# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Table-scoped standards checks feed actual quality and deterministic report endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.standard_reporting_models import StandardsQuality
from datakeel.harness.standard_cases import seed_standard_demo
from datakeel.quality.models import ReportView
from datakeel.storage.database import Database


def test_quality_and_report_endpoints_use_the_same_confirmed_table_population(
    db: Database, tmp_path: Path
) -> None:
    """Clean mapped columns score fully while deliberate failures enter their dimensions."""
    seed_standard_demo(db, tmp_path / "source")
    with TestClient(create_app(db)) as client:
        clean = client.get(
            "/api/standards/quality", params={"table_id": "standards_demo/main/clean_customers"}
        )
        assert clean.status_code == 200
        quality = StandardsQuality.model_validate(clean.json())
        assert quality.total == 100
        assert quality.column_count == 9
        assert quality.issues == ()
        dirty = client.get(
            "/api/standards/quality", params={"table_id": "standards_demo/main/dirty_customers"}
        )
        assert dirty.status_code == 200
        assert len(StandardsQuality.model_validate(dirty.json()).issues) == 9
        response = client.get(
            "/api/standards/analysis-report",
            params={"table_id": "standards_demo/main/dirty_customers"},
        )
        assert response.status_code == 200
        report = ReportView.model_validate(response.json())
        assert "dirty_customers/revenue" in report.body
        assert "[REDACTED]" in report.body
        assert "contact@example.org" not in report.body
        assert "9 failed rules" in report.baseline_verification


def test_empty_standards_quality_is_unmeasured(db: Database) -> None:
    """A fresh installation cannot display a passing data standard score."""
    with TestClient(create_app(db)) as client:
        response = client.get("/api/standards/quality")
        assert response.status_code == 200
        quality = StandardsQuality.model_validate(response.json())
        assert quality.total is None
        assert quality.grade == "unmeasured"
