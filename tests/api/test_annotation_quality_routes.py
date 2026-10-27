# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP annotation quality: import, AQL sampling, rework exports and signed acceptance."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.api.app import create_app
from datakeel.core.annotation_sampling import AnnotationQualityReport
from datakeel.storage.dataset_service import import_paths, list_versions
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from pydantic import JsonValue

    from datakeel.storage.database import Database

type Panel = tuple[TestClient, str, str, list[str]]


@pytest.fixture
def panel(db: Database, tmp_path: Path) -> Iterator[Panel]:
    """Twenty-four generated files; the HTTP client imports the reviews itself."""
    paths = [tmp_path / f"unit-{number:02d}.txt" for number in range(24)]
    for path in paths:
        path.write_text("Generated annotation review unit", encoding="utf-8")
    dataset = import_paths(db, "Generated annotation routes", paths)
    version = list_versions(db, dataset.id)[0]
    with TestClient(create_app(db)) as client:
        yield client, dataset.id, version.id, sorted(file.id for file in version.manifest)


def _batch(samples: list[str]) -> dict[str, JsonValue]:
    """Three reviewers agree except for one minority label on the first unit."""
    records: list[JsonValue] = [
        {
            "sample_id": sample,
            "annotator_id": reviewer,
            "labels": ["ferry" if (index, reviewer) == (0, "reviewer-c") else "tug"],
        }
        for index, sample in enumerate(samples)
        for reviewer in ("reviewer-a", "reviewer-b", "reviewer-c")
    ]
    return {"annotations": records}


def _import(panel: Panel, key: str) -> dict[str, JsonValue]:
    client, dataset_id, version_id, samples = panel
    imported = client.post(
        f"/api/datasets/{dataset_id}/annotation-quality/batches",
        json={"version_id": version_id, "batch": _batch(samples), "idempotency_key": key},
    )
    assert imported.status_code == 201, imported.text
    return imported.json()


def _sample(panel: Panel, batch_id: JsonValue) -> dict[str, JsonValue]:
    client, dataset_id, _version_id, _samples = panel
    request = {"batch_id": batch_id, "method": "aql", "aql": 6.5, "seed": 7}
    path = f"/api/datasets/{dataset_id}/annotation-quality/samples"
    plan = client.post(path, json=request)
    assert plan.status_code == 201, plan.text
    assert client.post(path, json=request).json()["sample_ids"] == plan.json()["sample_ids"]
    return plan.json()


def test_import_findings_and_rework_exports_over_http(panel: Panel) -> None:
    """An imported panel is measured once and its repair list downloads as CSV or JSON."""
    client, dataset_id, version_id, samples = panel
    base = f"/api/datasets/{dataset_id}/annotation-quality"
    report = _import(panel, "routes")
    findings = AnnotationQualityReport.model_validate(report).result.findings
    # One "ferry" among 72 labels is both a panel minority and a singleton category.
    assert sorted(item.code for item in findings) == ["minority_label", "rare_category"]
    assert {(item.sample_id, item.annotator_id) for item in findings} == {
        (samples[0], "reviewer-c")
    }
    overview = client.get(base, params={"version_id": version_id}).json()
    assert overview["latest"]["id"] == report["id"]
    csv = client.get(f"{base}/rework/{report['id']}", params={"format": "csv"})
    assert csv.headers["content-type"].startswith("text/csv")
    assert "annotation-rework.csv" in csv.headers["content-disposition"]
    assert "minority_label" in csv.text
    assert "minority_label" in client.get(f"{base}/rework/{report['id']}").text


def test_aql_sample_follows_the_table_arrow_and_repeats_over_http(panel: Panel) -> None:
    """Lot 24 is letter C; AQL 6.5 follows the arrow to D: n=8, Ac=1, Re=2, same seed same units."""
    sampled = _sample(panel, _import(panel, "aql-plan")["id"])
    assert (sampled["code_letter"], sampled["effective_code_letter"]) == ("C", "D")
    assert (sampled["sample_size"], sampled["acceptance_number"]) == (8, 1)
    assert sampled["rejection_number"] == 2


def test_acceptance_needs_matching_scope_and_a_signature_over_http(panel: Panel) -> None:
    """Preparing is not accepting: execution is refused until the existing approval endpoint."""
    client, dataset_id, version_id, samples = panel
    base = f"/api/datasets/{dataset_id}/annotation-quality"
    report = _import(panel, "acceptance")
    sampled = _sample(panel, report["id"])
    units = sampled["sample_ids"]
    assert isinstance(units, list)
    params = {
        "dataset_id": dataset_id,
        "version_id": version_id,
        "batch_id": report["id"],
        "sampling_id": sampled["id"],
        "checks": [
            {"sample_id": unit, "defective": index < 2, "reason": "Wrong class" * (index < 2)}
            for index, unit in enumerate(units)
        ],
    }
    mismatch = client.post(
        f"/api/datasets/{samples[0]}/annotation-quality/acceptance/prepare", json=params
    )
    assert mismatch.status_code == 422
    assert "does not match" in mismatch.json()["detail"]
    action = client.post(f"{base}/acceptance/prepare", json=params).json()
    assert (action["action_type"], action["reversible"]) == ("annotation_acceptance", False)
    execute = f"/api/actions/{action['id']}/execute"
    digest = {"plan_digest": action["plan_digest"]}
    assert client.post(execute, json=digest).status_code == 403
    assert client.get(base).json()["inspections"] == []
    approval = client.post(f"/api/approvals/{action['id']}", json={"approve": True, **digest})
    assert approval.status_code == 200, approval.text
    assert client.post(execute, json=digest).status_code == 200
    inspection = client.get(base).json()["inspections"][0]
    assert (inspection["accepted"], inspection["defective_count"]) == (False, 2)


def test_unknown_dataset_and_unsupported_aql_column_are_rejected(panel: Panel) -> None:
    """Missing datasets are 404 and AQL values outside the declared table fail explicitly."""
    client, dataset_id, _version_id, _samples = panel
    assert client.get("/api/datasets/missing/annotation-quality").status_code == 404
    report = _import(panel, "aql")
    response = client.post(
        f"/api/datasets/{dataset_id}/annotation-quality/samples",
        json={"batch_id": report["id"], "method": "aql", "aql": 3.0},
    )
    assert response.status_code == 422
    assert "0.01" in response.json()["detail"]
