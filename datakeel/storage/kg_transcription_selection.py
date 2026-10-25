# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Choose image replay defaults from immutable hashes without decoding or transcription."""

from pathlib import Path

from datakeel.core.kg_queries import KGTranscriptionSelection
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_files
from datakeel.storage.evidence_import import IMAGE_SUFFIXES
from datakeel.transcription.loader import get_profile, read_recording


def transcription_selection(
    db: Database, dataset_id: str, version_id: str
) -> KGTranscriptionSelection:
    """Require an explicit choice whenever even one image is absent from demo replay."""
    images = tuple(
        file
        for file in list_files(db, dataset_id, version_id)
        if Path(file.filename).suffix.lower() in IMAGE_SUFFIXES
    )
    if not images:
        return KGTranscriptionSelection(image_count=0)
    profile = get_profile("replay-image-demo")
    _, recording = read_recording(profile)
    hashes: set[str] = (
        {
            record.image_hash
            for record in recording.records
            if profile.mode == "ocr" or record.backend != "ocr"
        }
        if recording
        else set()
    )
    return KGTranscriptionSelection(
        image_count=len(images),
        default_profile_id=profile.id if all(file.sha256 in hashes for file in images) else None,
    )
