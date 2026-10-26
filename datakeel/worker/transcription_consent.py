# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check each visual transfer against the exact envelope frozen before approval."""

from datakeel.core.kg_execution import KGDocument, KGJob
from datakeel.core.transcription_errors import TranscriptionUnavailableError
from datakeel.core.transcription_models import ImageInput
from datakeel.storage.transcription_pricing import transcription_external


def authorize_image_transfer(job: KGJob, document: KGDocument, image: ImageInput) -> None:
    """Reject an unlisted image before transport without preventing other images completing."""
    prepared, source = job.prepared, document.image
    profile, estimate = prepared.transcription_profile, prepared.transcription_estimate
    if profile is None or not transcription_external(profile):
        return
    if (
        source is not None
        and estimate is not None
        and any(
            entry.file_id == source.asset_ref.asset_id
            and entry.image_hash == image.image_hash
            and entry.mode in {"auto", "vlm"}
            for entry in estimate.possible_external_images
        )
    ):
        return
    message = "Image is absent from the approved outbound image list"
    raise TranscriptionUnavailableError(message, reason="outbound_not_approved")
