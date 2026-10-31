# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated rectangle images and a recorded OpenAI-compatible vision server for prelabel tests.

The fake server decodes each sent JPEG and boxes its bright red rectangle, so mirrored views agree
exactly like a consistent model would. Image widths are unique per sample, which lets a test
script timeouts, rate limits or bad JSON for one image regardless of thread ordering. No test
ever reaches a real provider or reads a real credential.
"""

import base64
import json
import threading
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import cast

import httpx
from PIL import Image

from datakeel.core.production_models import ProductionTask, Project
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.production_queries import list_tasks
from tests.workbench_helpers import run_action

FIXTURE_CREDENTIAL = (
    "fixture-credential-value-7c41"  # Not a real key; only the fake server sees it.
)
CREDENTIAL_ENV = "DATAKEEL_TEST_PRELABEL_KEY"
BASE_URL = "https://vision.invalid/compatible-mode/v1"
_RED = 200


def image_width(index: int) -> int:
    """Give every generated sample a distinct width the fake server can recognise."""
    return 96 + index * 8


def seed_cloud_project(  # Tests vary count, tier, template kind and label mode.
    db: Database,
    directory: Path,
    count: int = 4,
    tier: str = "personal",
    kind: str = "box",
    label_mode: str | None = None,
) -> tuple[Project, tuple[ProductionTask, ...]]:
    """Create ``count`` images with one red rectangle each and a project over them."""
    directory.mkdir(parents=True)
    paths: list[Path] = []
    for index in range(count):
        path = directory / f"rect-{index}.png"
        with Image.new("RGB", (image_width(index), 80), (20, 40, 60)) as image:
            image.paste((255, 0, 0), (8 + index, 10, 40 + index, 50))
            image.save(path)
        paths.append(path)
    dataset = import_paths(db, "Generated prelabel", paths)
    version = list_versions(db, dataset.id)[0]
    labels = [{"id": "cat", "name": "Cat"}, {"id": "dog", "name": "Dog"}]
    run_action(db, "create_label_set", {"label_set_id": "pl-labels", "labels": labels})
    run_action(db, "publish_label_set", {"label_set_id": "pl-labels", "version": 1})
    config = {"label_mode": label_mode} if label_mode else {}
    template = {"id": "pl-template", "name": "Prelabel", "annotation_type": kind}
    run_action(
        db,
        "create_label_set",
        {"target": "template", "template": {**template, "component_config": config}},
    )
    project = Project.model_validate(
        run_action(
            db,
            "create_project",
            {
                "name": "Prelabel",
                "dataset_id": dataset.id,
                "version_id": version.id,
                "label_set_id": "pl-labels",
                "template_id": "pl-template",
                "workflow_tier": tier,
            },
        ).root
    )
    run_action(db, "split_packages", {"project_id": project.id, "package_size": 100})
    return project, list_tasks(db, project.id)


def cloud_model(model_id: str = "vision", **cloud: object) -> dict[str, object]:
    """Return a register_model payload for a priced cloud model on the fake endpoint."""
    settings: dict[str, object] = {
        "base_url": BASE_URL,
        "model": "fixture-vl",
        "credential_env": CREDENTIAL_ENV,
        "input_price": 0.2,
        "output_price": 2.0,
        "prompt_tokens": 300,
        "expected_output_tokens": 60,
        **cloud,
    }
    return {
        "id": model_id,
        "name": "fixture-vl",
        "version": "2026-10",
        "provider": "cloud",
        "capabilities": ["box", "classification"],
        "currency": "CNY",
        "cloud": settings,
    }


def _decode(body: Mapping[str, object]) -> Image.Image:
    messages = cast("list[dict[str, list[dict[str, dict[str, str]]]]]", body["messages"])
    url = messages[0]["content"][0]["image_url"]["url"]
    return Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")


def _red_box(image: Image.Image) -> list[int] | None:
    pixels = image.load()
    assert pixels is not None
    found = [
        (x, y)
        for y in range(image.height)
        for x in range(image.width)
        if pixels[x, y][0] > _RED and pixels[x, y][1] < _RED // 2  # type: ignore[index]
    ]
    if not found:
        return None
    xs, ys = [x for x, _ in found], [y for _, y in found]
    return [
        round(min(xs) * 1000 / image.width),
        round(min(ys) * 1000 / image.height),
        round((max(xs) + 1) * 1000 / image.width),
        round((max(ys) + 1) * 1000 / image.height),
    ]


class FakeVision:
    """Answer chat-completions requests like a consistent box model, with scripted failures."""

    def __init__(
        self,
        failures: Mapping[int, str] | None = None,
        confidence: float | Mapping[int, float] = 0.9,
        usage: tuple[int, int] | None = (400, 50),
    ) -> None:
        """Script per-sample failures and reported confidence by sample index.

        Failures are ``timeout``, ``network``, ``429``, ``500``, ``prose`` or ``empty``.
        """
        self.failures = dict(failures or {})
        self.confidence = confidence
        self.usage = usage
        self.requests: list[dict[str, object]] = []
        self.authorizations: list[str] = []
        self._lock = threading.Lock()

    def index_of(self, image: Image.Image) -> int:
        """Recover the sample index from the unique generated width."""
        return (image.width - 96) // 8

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Record the request, then answer or fail as scripted for that sample."""
        body = json.loads(request.content)
        with self._lock:
            self.requests.append(body)
            self.authorizations.append(request.headers.get("authorization", ""))
        image = _decode(body)
        failure = self.failures.get(self.index_of(image))
        if failure == "timeout":
            message = "scripted"
            raise httpx.ReadTimeout(message, request=request)
        if failure == "network":
            message = "scripted"
            raise httpx.ConnectError(message, request=request)
        if failure in {"429", "500"}:
            return httpx.Response(int(failure), json={"error": {"message": "scripted"}})
        index = self.index_of(image)
        confidence = (
            self.confidence.get(index, 0.9)
            if isinstance(self.confidence, Mapping)
            else self.confidence
        )
        box = None if failure == "empty" else _red_box(image)
        objects = [{"label": "Cat", "box": box, "confidence": confidence}] if box else []
        text = "Sure!" if failure == "prose" else json.dumps({"objects": objects})
        reply: dict[str, object] = {"choices": [{"message": {"content": text}}]}
        if self.usage is not None:
            reply["usage"] = {"prompt_tokens": self.usage[0], "completion_tokens": self.usage[1]}
        return httpx.Response(200, json=reply)
