# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training HTTP reads, immutable saves, imports and guarded artifact downloads."""

from __future__ import annotations

import io
import tarfile
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ActionPlan
from datakeel.api.app import create_app
from datakeel.core.training_models import LeakageReport, SplitComparison, SplitSet
from datakeel.harness.training_cases import seed_training_case
from datakeel.storage.database import data_dir
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from datakeel.core.harness_eval import CaseFixture
    from datakeel.storage.database import Database

type TrainingPanel = tuple[TestClient, str, CaseFixture]


@pytest.fixture
def panel(db: Database, tmp_path: Path) -> Iterator[TrainingPanel]:
    """A balanced generated version includes one independent external directory leak."""
    fixture = seed_training_case(db, tmp_path)
    base = f"/api/datasets/{fixture.dataset_id}/versions/{fixture.version_id}/training"
    with TestClient(create_app(db)) as client:
        yield client, base, fixture


def _save(client: TestClient, base: str, name: str, *, directory: bool = False) -> SplitSet:
    response = client.post(
        f"{base}/splits",
        json={"name": name, "source": "directory" if directory else "generated"},
    )
    assert response.status_code == 201, response.text
    return SplitSet.model_validate(response.json())


def test_preview_is_reproducible_and_does_not_save_splits(panel: TrainingPanel) -> None:
    """Preview measurements expose exact balanced counts and preserve an empty saved list."""
    client, base, _fixture = panel
    first = client.post(f"{base}/preview", json={"name": "eight-one-one"})
    assert first.status_code == 200, first.text
    assert client.post(f"{base}/preview", json={"name": "eight-one-one"}).json() == first.json()
    assert client.get(f"{base}/splits").json() == []
    split = SplitSet.model_validate(first.json())
    assert [value.count for value in split.distributions] == [80, 10, 10]
    assert [[label.count for label in value.labels] for value in split.distributions] == [
        [40, 40],
        [5, 5],
        [5, 5],
    ]
    assert "object_key" not in first.text


def test_saved_splits_are_named_immutable_and_version_scoped(panel: TrainingPanel) -> None:
    """Retries reuse the same snapshot; a name cannot be rebound to another seed or version."""
    client, base, fixture = panel
    split = _save(client, base, "baseline")
    assert _save(client, base, "baseline") == split
    assert client.get(f"{base}/splits").json()[0]["id"] == split.id
    assert client.get(f"{base}/splits/{split.id}").json() == split.model_dump(mode="json")
    assert client.post(f"{base}/splits", json={"name": "baseline", "seed": 3}).status_code == 409
    other = base.replace(fixture.version_id, "missing-version")
    assert client.get(f"{other}/splits/{split.id}").status_code == 404
    assert client.get(f"{base}/splits/missing").status_code == 404


def test_external_leakage_has_direct_evidence_and_generated_splits_avoid_it(
    panel: TrainingPanel,
) -> None:
    """Directory assignments remain unchanged for inspection, while new splits join duplicates."""
    client, base, _fixture = panel
    external = _save(client, base, "external", directory=True)
    report = LeakageReport.model_validate(client.get(f"{base}/splits/{external.id}/leakage").json())
    assert sorted(pair.kind for pair in report.pairs) == ["exact", "image"]
    assert all(pair.distance == 0 and pair.detail for pair in report.pairs)
    assert all({pair.left_split, pair.right_split} == {"train", "val"} for pair in report.pairs)
    preview = client.post(f"{base}/leakage", json={"name": "read", "source": "directory"})
    assert LeakageReport.model_validate(preview.json()).pairs == report.pairs
    generated = _save(client, base, "safe")
    assert client.get(f"{base}/splits/{generated.id}/leakage").json()["pairs"] == []
    comparison = SplitComparison.model_validate(
        client.get(f"{base}/compare", params={"left": external.id, "right": generated.id}).json()
    )
    assert comparison.changed_sample_ids
    assert sum(value.count for value in comparison.left) == 100
    assert sum(value.count for value in comparison.right) == 100


def test_training_import_accepts_standard_coco_and_yolo(panel: TrainingPanel) -> None:
    """Both typed formats append real version-owned annotations through the review store."""
    client, base, fixture = panel
    coco = client.post(
        f"{base}/import-annotations",
        json={
            "format": "coco",
            "idempotency_key": "coco-import",
            "coco": {
                "images": [{"id": 7, "file_name": "external.png", "width": 32, "height": 32}],
                "categories": [{"id": 9, "name": "vessel"}],
                "annotations": [{"id": 13, "image_id": 7, "category_id": 9, "bbox": [1, 2, 3, 4]}],
            },
            "sample_ids": {"external.png": fixture.file_id},
        },
    )
    assert coco.status_code == 201, coco.text
    assert coco.json()["sample_count"] == 1
    yolo = client.post(
        f"{base}/import-annotations",
        json={
            "format": "yolo",
            "idempotency_key": "yolo-import",
            "yolo": {
                "names": ["vessel"],
                "images": [
                    {
                        "sample_id": fixture.file_id,
                        "width": 32,
                        "height": 32,
                        "labels": "0 0.5 0.5 0.25 0.25\n",
                    }
                ],
            },
        },
    )
    assert yolo.status_code == 201, yolo.text
    assert yolo.json()["annotation_count"] == 1


def test_deferred_hf_training_format_is_rejected(panel: TrainingPanel) -> None:
    """Preparing an export cannot bypass the retained-format boundary."""
    client, _base, fixture = panel
    response = client.post(
        "/api/actions/export_dataset/prepare",
        json={
            "dataset_id": fixture.dataset_id,
            "version_id": fixture.version_id,
            "format": "hf_imagefolder",
        },
    )
    assert response.status_code == 422, response.text
    assert "format" in response.text


def _export(panel: TrainingPanel) -> ActionPlan:
    client, base, fixture = panel
    split = _save(client, base, "export")
    response = client.post(
        "/api/actions/export_dataset/prepare",
        json={
            "dataset_id": fixture.dataset_id,
            "version_id": fixture.version_id,
            "split_set_id": split.id,
            "format": "imagefolder",
        },
    )
    assert response.status_code == 200, response.text
    plan = ActionPlan.model_validate(response.json())
    assert client.get(f"/api/actions/{plan.id}/export").status_code == 404
    approval = client.post(
        f"/api/approvals/{plan.id}", json={"plan_digest": plan.plan_digest, "approve": True}
    )
    assert approval.status_code == 200, approval.text
    executed = client.post(
        f"/api/actions/{plan.id}/execute", json={"plan_digest": plan.plan_digest}
    )
    assert executed.status_code == 200, executed.text
    return plan


def test_completed_training_artifact_downloads_a_real_archive(panel: TrainingPanel) -> None:
    """The browser download resolves only a successful receipt in the controlled directory."""
    client, _base, _fixture = panel
    plan = _export(panel)
    response = client.get(f"/api/actions/{plan.id}/export")
    assert response.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(response.content)) as archive:
        assert "MANIFEST.json" in archive.getnames()
        assert "classes.json" in archive.getnames()
        assert any(
            len(name.split("/")) == 3
            and name.split("/")[0] in {"train", "val", "test"}
            and name.endswith(".png")
            for name in archive.getnames()
        )


def test_export_download_rejects_symlink_and_missing_artifacts(panel: TrainingPanel) -> None:
    """A successful receipt cannot be repurposed to download another local file."""
    client, _base, _fixture = panel
    plan = _export(panel)
    root = data_dir() / "exports"
    target = next(root.iterdir())
    content = target.read_bytes()
    target.unlink()
    assert client.get(f"/api/actions/{plan.id}/export").status_code == 404
    other = root.parent / "other.tar"
    other.write_bytes(content)
    target.symlink_to(other)
    assert client.get(f"/api/actions/{plan.id}/export").status_code == 404
