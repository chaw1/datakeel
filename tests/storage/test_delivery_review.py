# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dataset delivery signs a corrected snapshot and archives its checked split."""

import tarfile
from pathlib import Path
from typing import NamedTuple

import pytest
from PIL import Image

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.delivery_models import DeliveryManifest
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.core.training_models import SplitRequest
from datakeel.dataset_store.dataset_service import list_versions
from datakeel.storage.database import Database
from datakeel.storage.delivery_service import export_release
from datakeel.storage.evidence_import import import_evidence_samples
from datakeel.storage.release_service import get_release
from datakeel.storage.training_store import create_split


class Imported(NamedTuple):
    """Identities of the retained and duplicated fixture samples."""

    dataset: str
    version: str
    retained: list[str]


@pytest.fixture
def imported(db: Database, tmp_path: Path) -> Imported:
    """Import two matching images and one different image into two directories."""
    for split, name, color in (
        ("train", "left", "navy"),
        ("test", "duplicate", "navy"),
        ("test", "right", "orange"),
    ):
        folder = tmp_path / split
        folder.mkdir(exist_ok=True)
        Image.new("RGB", (16, 16), color).save(folder / f"{name}.png")
    dataset = import_evidence_samples(db, "Generated review samples", tmp_path)
    version = list_versions(db, dataset.id)[0]
    kept = [file.id for file in version.manifest if "duplicate" not in file.filename]
    return Imported(dataset.id, version.id, kept)


def _draft(fixture: Imported, version: str, split: str, baseline: str | None) -> JsonDocument:
    return JsonDocument(
        {
            "dataset_id": fixture.dataset,
            "version_id": version,
            "tag": "1.0.0",
            "delivery_review": {"split_id": split, "baseline_version_id": baseline},
        }
    )


def test_signed_correction_carries_verified_review_into_delivery(
    db: Database, imported: Imported, tmp_path: Path
) -> None:
    """Reject leaking input, correct through a new immutable version, then sign an archive."""
    policy = SplitRequest(name="Delivery review", source="directory")
    leaking = create_split(db, imported.dataset, imported.version, policy)
    with pytest.raises(ConflictError, match="cross-split leakage"):
        prepare_action(db, "publish_release", _draft(imported, imported.version, leaking.id, None))
    correction = prepare_action(
        db,
        "create_version_from_selection",
        JsonDocument.model_validate(
            {
                "selection": {
                    "dataset_id": imported.dataset,
                    "version_ids": [imported.version],
                    "filters": [{"field": "id", "operator": "in", "value": imported.retained}],
                    "object_type": "file",
                }
            }
        ),
    )
    corrected = execute_plan(db, correction.id, ExecuteRequest(plan_digest=correction.plan_digest))
    assert corrected.receipt is not None
    version = corrected.receipt.outputs[0].asset_id
    with pytest.raises(NotFoundError, match="candidate version"):
        prepare_action(db, "publish_release", _draft(imported, version, leaking.id, None))
    clean = create_split(db, imported.dataset, version, policy)
    plan = prepare_action(
        db, "publish_release", _draft(imported, version, clean.id, imported.version)
    )
    request = ExecuteRequest(plan_digest=plan.plan_digest)
    with pytest.raises(AuthorizationError):
        execute_plan(db, plan.id, request)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    result = execute_plan(db, plan.id, request)
    assert result.receipt is not None
    release = get_release(db, result.receipt.outputs[0].asset_id)
    review = release.metadata["delivery_review"]
    assert isinstance(review, dict)
    assert (review["version_id"], review["split_id"], review["sample_count"]) == (
        version,
        clean.id,
        2,
    )
    assert review["baseline_version_id"] == imported.version
    archive_path = export_release(db, release.id, tmp_path / "approved.tar.gz")
    with tarfile.open(archive_path) as archive:
        manifest = archive.extractfile("MANIFEST.json")
        assert manifest is not None
        exported = DeliveryManifest.model_validate_json(manifest.read())
    assert exported.metadata["delivery_review"] == review
    assert exported.file_count == release.file_count == 2


def test_delivery_review_rejects_nonstandard_policy_and_invalid_baseline(
    db: Database, imported: Imported
) -> None:
    """User-provided split rules or a matching baseline cannot certify the candidate."""
    weak = create_split(
        db,
        imported.dataset,
        imported.version,
        SplitRequest(name="Weakened checks", source="directory", image_threshold=0),
    )
    with pytest.raises(ValidationError, match="standard directory"):
        prepare_action(db, "publish_release", _draft(imported, imported.version, weak.id, None))
    with pytest.raises(ValidationError, match="baseline must differ"):
        prepare_action(
            db, "publish_release", _draft(imported, imported.version, weak.id, imported.version)
        )
