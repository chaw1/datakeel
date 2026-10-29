# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP and OpenAPI expose the shared source enum without opening a database."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI

from datakeel.api.routes.training import router
from datakeel.core.models import utcnow
from datakeel.core.training_models import SplitRequest, SplitSet
from datakeel.storage.database import Database
from tests.asgi_client import TestClient


def test_http_preview_forwards_annotation_sources_and_rejects_unknown_values() -> None:
    """A typed HTTP request reaches the same policy used by storage and the CLI."""
    app = FastAPI()
    app.state.db = MagicMock(spec=Database)
    app.include_router(router)
    with TestClient(app) as client:
        for source in ("all", "classification", "detection", "spans"):
            request = SplitRequest(name="http", stratification_source=source)
            result = SplitSet(
                id="split",
                dataset_id="dataset",
                version_id="version",
                request=request,
                members=(),
                distributions=(),
                created_at=utcnow(),
            )
            with patch(
                "datakeel.api.routes.training.preview_split", return_value=result
            ) as preview:
                response = client.post(
                    "/api/datasets/dataset/versions/version/training/preview",
                    json={"name": "http", "stratification_source": source},
                )
            assert response.status_code == 200
            assert SplitSet.model_validate(response.json()).request == request
            forwarded = preview.call_args.args[3]
            assert isinstance(forwarded, SplitRequest)
            assert forwarded.stratification_source == source
        invalid = client.post(
            "/api/datasets/dataset/versions/version/training/preview",
            json={"name": "invalid", "stratification_source": "boxes"},
        )
        assert invalid.status_code == 422
    schema = app.openapi()
    assert schema["components"]["schemas"]["StratificationSource"]["enum"] == [
        "all",
        "classification",
        "detection",
        "spans",
    ]
