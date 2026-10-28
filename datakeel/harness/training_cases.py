# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate labelled local images with one known cross-directory duplicate."""

import hashlib
from pathlib import Path

from PIL import Image

from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord
from datakeel.core.annotation_sampling import AnnotationImportRequest
from datakeel.core.harness_eval import CaseFixture
from datakeel.storage.annotation_store import import_annotations
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import import_evidence_samples, source_manifest

_TRAIN_SIZE = 80
_TRAIN_VAL_SIZE = 90


def seed_training_case(db: Database, directory: Path) -> CaseFixture:
    """Import 100 noise images, two balanced classes and one exact validation leak."""
    root = directory / "training"
    for index in range(100):
        split = "train" if index < _TRAIN_SIZE else "val" if index < _TRAIN_VAL_SIZE else "test"
        path = root / split / f"sample-{index:03d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Reuse only this image; expected leakage is measured by the production code.
        pixel_seed = 0 if index == _TRAIN_SIZE else index
        pixels = hashlib.shake_256(str(pixel_seed).encode()).digest(32 * 32 * 3)
        Image.frombytes("RGB", (32, 32), pixels).save(path)
    dataset = import_evidence_samples(db, "Generated training golden fixture", root)
    version_id, files = source_manifest(db, dataset.id)
    import_annotations(
        db,
        dataset.id,
        AnnotationImportRequest(
            version_id=version_id,
            idempotency_key="training-golden-labels",
            batch=AnnotationBatch(
                annotations=tuple(
                    AnnotationRecord(
                        sample_id=file.id,
                        annotator_id="reviewer",
                        labels=("even" if int(Path(file.filename).stem[-3:]) % 2 == 0 else "odd",),
                    )
                    for file in files
                )
            ),
        ),
    )
    return CaseFixture(dataset_id=dataset.id, version_id=version_id, file_id=files[0].id)
