# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import portable training detections through existing immutable annotation batches."""

from collections import Counter

from datakeel.core.annotation_models import AnnotationBatch
from datakeel.core.annotation_sampling import AnnotationImportRequest, AnnotationQualityReport
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.training_export_models import TrainingAnnotationImport
from datakeel.storage.annotation_frames import sample_geometry
from datakeel.storage.annotation_store import import_annotations, require_annotation_version
from datakeel.storage.database import Database
from datakeel.storage.prediction_frames import upright_import
from datakeel.storage.training_inputs import authorize_training
from datakeel.training.importers import import_coco, import_yolo
from datakeel.training.native import import_annotations_jsonl


def import_training_annotations(
    db: Database,
    dataset_id: str,
    version_id: str,
    request: TrainingAnnotationImport,
    *,
    access: AccessContext | None = None,
) -> AnnotationQualityReport:
    """Resolve external image filenames to version members and append a typed batch."""
    with db.session() as session:
        authorize_training(session, dataset_id, version_id, access)
        version = require_annotation_version(session, dataset_id, version_id)
        filenames = {str(item["filename"]): str(item["id"]) for item in version.manifest}
        # Ambiguous filenames require an explicit map, rather than choosing one silently.
        counts = Counter(str(item["filename"]) for item in version.manifest)
        repeated = {name for name, count in counts.items() if count > 1}
        mapping = {name: identity for name, identity in filenames.items() if name not in repeated}
        mapping.update(request.sample_ids)
    annotations = (
        import_coco(request.coco, request.annotator_id, mapping)
        if request.coco is not None
        else import_yolo(request.yolo, request.annotator_id)
        if request.yolo is not None
        else import_annotations_jsonl(request.annotations_jsonl)
        if request.annotations_jsonl is not None
        else ()
    )
    with db.session() as session:
        upright = tuple(
            upright_import(
                record,
                sample_geometry(session, version_id, record.sample_id),
                request.coordinate_frame,
                normalized=request.yolo is not None,
            )
            for record in annotations
        )
    return import_annotations(
        db,
        dataset_id,
        AnnotationImportRequest(
            version_id=version_id,
            name=request.name,
            idempotency_key=request.idempotency_key,
            batch=AnnotationBatch(annotations=upright),
        ),
    )
