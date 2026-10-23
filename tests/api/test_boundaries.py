# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP schema, dependency, and error-boundary regressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datakeel.core.errors import DatakeelError
    from datakeel.storage.database import Database

import asyncio

import pytest
from pydantic import ValidationError as PydanticValidationError
from starlette.requests import Request

from datakeel.api.app import create_app
from datakeel.api.errors import domain_error
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.storage.dataset_service import DatasetInput
from tests.api.test_workflows import dataset
from tests.asgi_client import TestClient


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (NotFoundError("missing"), 404),
        (ConflictError("conflict"), 409),
        (AuthorizationError("denied"), 403),
        (ValidationError("invalid"), 422),
    ],
)
def test_error_mapping_for_domain_failure_returns_declared_status(
    failure: DatakeelError, status: int
) -> None:
    """Verify error mapping for domain failure returns declared status."""
    request = Request({"type": "http"})
    assert asyncio.run(domain_error(request, failure)).status_code == status


def test_request_model_when_mutated_rejects_assignment() -> None:
    """Verify request model when mutated rejects assignment."""
    body = DatasetInput(name="sample")
    with pytest.raises(PydanticValidationError, match="frozen_instance"):
        body.name = "changed"


def test_openapi_responses_when_exported_include_concrete_models(db: Database) -> None:
    """Verify openapi responses when exported include concrete models."""
    schema = create_app(db).openapi()
    expected = {"DatasetView", "FileView", "TaskView", "GraphView", "QualityView", "ReportView"}
    assert expected <= schema["components"]["schemas"].keys()


def test_import_when_unknown_request_field_returns_validation_error(db: Database) -> None:
    """Verify import when unknown request field returns validation error."""
    with TestClient(create_app(db)) as client:
        response = client.post("/api/datasets", json={"name": "sample", "unexpected": True})
    assert response.status_code == 422


def test_import_when_base64_invalid_returns_validation_error(db: Database) -> None:
    """Verify import when base64 invalid returns validation error."""
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/api/datasets",
            json={"name": "sample", "files": [{"filename": "safe.txt", "content_base64": "!"}]},
        )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "suffix",
    ["/files?version=missing", "/files/missing/download"],
)
def test_dataset_resource_when_missing_returns_not_found(db: Database, suffix: str) -> None:
    """Verify dataset resource when missing returns not found."""
    with TestClient(create_app(db)) as client:
        identifier = dataset(client)
        response = client.get(f"/api/datasets/{identifier}{suffix}")
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/api/tasks/missing", "/api/tasks/missing/artifacts"])
def test_task_resource_when_missing_returns_not_found(db: Database, path: str) -> None:
    """Verify task resource when missing returns not found."""
    with TestClient(create_app(db)) as client:
        response = client.get(path)
    assert response.status_code == 404


def test_croissant_when_dataset_omitted_returns_validation_error(db: Database) -> None:
    """Verify croissant when dataset omitted returns validation error."""
    with TestClient(create_app(db)) as client:
        response = client.get("/api/export", params={"format": "croissant"})
    assert response.status_code == 422


def test_health_when_application_created_returns_ok(db: Database) -> None:
    """Verify health when application created returns ok."""
    with TestClient(create_app(db)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_admin_when_bundle_present_returns_html(db: Database) -> None:
    """Verify admin when bundle present returns html."""
    with TestClient(create_app(db)) as client:
        assert "<html" in client.get("/admin").text


def test_task_submission_when_key_reused_for_changed_target_returns_conflict(db: Database) -> None:
    """Verify task submission when key reused for changed target returns conflict."""
    with TestClient(create_app(db)) as client:
        first, second = dataset(client), dataset(client)
        client.post("/api/tasks", json={"dataset_id": first, "idempotency_key": "same"})
        response = client.post("/api/tasks", json={"dataset_id": second, "idempotency_key": "same"})
    assert response.status_code == 409


def test_task_listing_when_submitted_returns_typed_progress(db: Database) -> None:
    """Verify task listing when submitted returns typed progress."""
    with TestClient(create_app(db)) as client:
        identifier = dataset(client)
        submitted = client.post("/api/tasks", json={"dataset_id": identifier}).json()
        assert client.get("/api/tasks").json()[0]["id"] == submitted["id"]


def test_metadata_read_when_dataset_imported_retains_values_and_template(db: Database) -> None:
    """Verify metadata read when dataset imported retains values and template."""
    with TestClient(create_app(db)) as client:
        identifier = dataset(client)
        assert client.get(f"/api/datasets/{identifier}/metadata").json() == {
            "values": {},
            "template": None,
        }


def test_quality_config_when_boolean_size_returns_validation_error(db: Database) -> None:
    """Verify quality config when boolean size returns validation error."""
    with TestClient(create_app(db)) as client:
        identifier = dataset(client)
        response = client.put(
            f"/api/datasets/{identifier}/quality/config", json={"min_size_bytes": True}
        )
    assert response.status_code == 422
