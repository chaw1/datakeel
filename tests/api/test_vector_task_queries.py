# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional vector task reports survive the worker-store query split and HTTP schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.persistence.task_queries import list_tasks, query_task
from datakeel.persistence.task_queue import DatabaseQueue
from datakeel.worker_store import task_queries as worker_queries
from tests.asgi_client import TestClient
from tests.evidence.vector_helpers import vector_dataset, vector_run

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_openapi_and_query_list_keep_optional_vector_and_partial_success(
    db: Database, tmp_path: Path
) -> None:
    """A partial vector product has the same typed status in single/list HTTP responses."""
    dataset = vector_dataset(db, tmp_path, (b"one", b"\xff", b"three"))
    partial = vector_run(db, dataset)
    plain_id = DatabaseQueue(db).submit(dataset, "plain")
    assert partial.vector is not None
    assert partial.vector.status == "partial_success"
    assert partial.partial
    assert worker_queries.query_task(db, partial.id).vector is None
    assert not worker_queries.query_task(db, partial.id).partial
    listed = list_tasks(db)
    assert [view.id for view in listed] == [plain_id, partial.id]
    assert listed[1] == query_task(db, partial.id)
    with TestClient(create_app(db)) as client:
        schema = client.get("/api/openapi.json").json()
        task_schema = schema["components"]["schemas"]["TaskView"]["properties"]
        assert task_schema["vector"]["anyOf"] == [
            {"$ref": "#/components/schemas/VectorTaskReport"},
            {"type": "null"},
        ]
        assert "vector" not in schema["components"]["schemas"]["TaskView"]["required"]
        single = client.get(f"/api/tasks/{partial.id}")
        assert single.status_code == 200
        assert single.json()["vector"]["status"] == "partial_success"
        assert single.json()["partial"] is True
        tasks = client.get("/api/tasks").json()
        assert tasks[1] == single.json()
        assert "vector" not in tasks[0]
