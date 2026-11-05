# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen split export preparation rejects segments before modality filtering."""

from collections.abc import Callable
from datetime import UTC, datetime

from datakeel.actions.parameters import ExportParams
from datakeel.core.annotation_models import AnnotationRecord, AnnotationSegment
from datakeel.core.errors import ValidationError
from datakeel.core.training_models import SplitMember, SplitRequest, SplitSet
from datakeel.dataset_store.rows import VersionRow
from datakeel.storage.annotation_frames import DISPLAY_FRAME
from datakeel.storage.database import Database
from datakeel.storage.training_export import training_export_inputs
from datakeel.storage.training_rows import TrainingSplitRow
from tests.storage.production_catalog_fixtures import catalog_project


def _reject(call: Callable[[], object], match: str) -> None:
    message = None
    try:
        call()
    except ValidationError as error:
        message = str(error)
    assert message is not None, "Expected segment export preparation to reject the operation"
    assert match in message


def _split(db: Database) -> SplitSet:
    catalog_project(db)
    with db.session() as session:
        version = session.get(VersionRow, "catalog-source")
        assert version is not None
        version.manifest = [
            {
                **raw,
                "modality": "audio",
                "metadata": {"media_probe": {"duration_ms": 1000, "codec": "pcm_s16le"}},
            }
            for raw in version.manifest
        ]
        members = tuple(
            SplitMember(
                sample_id=str(raw["id"]),
                split="train",
                annotations=(
                    AnnotationRecord(
                        sample_id=str(raw["id"]),
                        annotator_id="ann",
                        segments=(AnnotationSegment(category="a", start_ms=0, end_ms=1000),),
                        media_duration_ms=1000,
                    ),
                ),
                sha256="",
            )
            for raw in version.manifest
        )
        split = SplitSet(
            id="segments-split",
            dataset_id="catalog-data",
            version_id="catalog-source",
            request=SplitRequest(name="segments"),
            members=members,
            distributions=(),
            created_at=datetime(1970, 1, 1, tzinfo=UTC),
        )
        session.add(
            TrainingSplitRow(
                id=split.id,
                dataset_id=split.dataset_id,
                version_id=split.version_id,
                name="segments",
                created_at=0,
                payload=split.model_dump(mode="json"),
                samples=[],
                coordinate_frame=DISPLAY_FRAME,
            )
        )
        session.commit()
        return split


def test_prepare_rejects_all_frozen_segment_records_before_audio_filter(db: Database) -> None:
    """COCO cannot drop audio first and then report a successful empty/image-only export."""
    split = _split(db)
    with db.session() as session:
        _reject(
            lambda: training_export_inputs(
                session,
                ExportParams(
                    dataset_id="catalog-data",
                    version_id="catalog-source",
                    split_set_id=split.id,
                    format="coco",
                ),
                materialize=False,
            ),
            "webvtt or annotations_jsonl",
        )


def test_prepare_webvtt_selects_audio_and_video_sources(db: Database) -> None:
    """The new export format keeps probed media instead of using the image-only filter."""
    split = _split(db)
    with db.session() as session:
        export = training_export_inputs(
            session,
            ExportParams(
                dataset_id="catalog-data",
                version_id="catalog-source",
                split_set_id=split.id,
                format="webvtt",
            ),
            materialize=False,
        )
        assert len(export.items) == 2
        assert all(item.file.modality == "audio" for item in export.items)
