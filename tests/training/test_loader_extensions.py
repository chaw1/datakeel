# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training layouts must not silently lose normally imported images to loader suffix filters."""

from pathlib import Path

import pytest
from PIL import Image

from datakeel.actions.parameters import ExportParams
from datakeel.core.annotation_models import AnnotationBatch, AnnotationBox, AnnotationRecord
from datakeel.core.annotation_sampling import AnnotationImportRequest
from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import TrainingExport, TrainingFormat
from datakeel.core.training_models import SplitRequest
from datakeel.storage.annotation_store import import_annotations
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.training_export import training_export_inputs
from datakeel.storage.training_store import create_split
from datakeel.training.export import write_training_export


@pytest.fixture
def gif_export(db: Database, tmp_path: Path) -> TrainingExport:
    """Reach training through ordinary GIF intake and a real frozen single-label review."""
    source = tmp_path / "generated.gif"
    Image.new("RGB", (32, 32), (40, 90, 120)).save(source)
    dataset = import_paths(db, "Generated GIF loader boundary", [source])
    version = list_versions(db, dataset.id)[0]
    file = version.manifest[0]
    assert file.modality == "image"
    assert file.filename.endswith(".gif")
    import_annotations(
        db,
        dataset.id,
        AnnotationImportRequest(
            version_id=version.id,
            idempotency_key="gif-label",
            batch=AnnotationBatch(
                annotations=(
                    AnnotationRecord(
                        sample_id=file.id,
                        annotator_id="r",
                        labels=("class",),
                        boxes=(AnnotationBox(category="class", x1=1, y1=2, x2=20, y2=24),),
                    ),
                )
            ),
        ),
    )
    split = create_split(db, dataset.id, version.id, SplitRequest(name="gif"))
    with db.session() as session:
        return training_export_inputs(
            session,
            ExportParams(
                dataset_id=dataset.id,
                version_id=version.id,
                split_set_id=split.id,
                format="imagefolder",
            ),
            materialize=True,
        )


def _assert_gif_rejected(
    export: TrainingExport, format_name: TrainingFormat, tmp_path: Path
) -> None:
    archive = tmp_path / f"{format_name}.tar"
    caught: ValidationError | None = None
    try:
        write_training_export(
            export.model_copy(update={"format": format_name}), tmp_path / format_name, archive
        )
    except ValidationError as error:
        caught = error
    assert caught is not None, "A standard loader must never silently ignore an exported GIF"
    assert f"{format_name} does not support source image extension .gif" in str(caught)
    assert not archive.exists()


def test_imagefolder_rejects_normally_imported_gif(
    gif_export: TrainingExport, tmp_path: Path
) -> None:
    """Default torchvision ImageFolder excludes GIF despite ordinary intake accepting it."""
    _assert_gif_rejected(gif_export, "imagefolder", tmp_path)


def test_yolo_rejects_normally_imported_gif(gif_export: TrainingExport, tmp_path: Path) -> None:
    """The Ultralytics detection image list also excludes GIF rather than treating it as video."""
    _assert_gif_rejected(gif_export, "yolo", tmp_path)
