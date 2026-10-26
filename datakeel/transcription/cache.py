# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Hash complete transcription semantics independently of paths and credentials."""

import hashlib
import json

from datakeel.core.transcription_models import TranscriptionMode, TranscriptionProfile


def profile_digest(
    profile: TranscriptionProfile,
    recording_hash: str | None = None,
    mode: TranscriptionMode | None = None,
) -> str:
    """Bind model, OCR version, prompt, options, mode and exact replay bytes."""
    data = profile.model_dump(mode="json", exclude={"id", "recording", "api_key_env"})
    if (mode or profile.mode) != "auto":
        data.pop("auto_routing", None)
    data["model"] = profile.model
    data["mode"] = mode or profile.mode
    data["recording_hash"] = recording_hash
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def cache_key(
    image_hash: str,
    profile: TranscriptionProfile,
    recording_hash: str | None = None,
    mode: TranscriptionMode | None = None,
) -> str:
    """Locate a persisted transcription by source revision and frozen configuration."""
    return hashlib.sha256(
        f"{image_hash}:{profile_digest(profile, recording_hash, mode)}".encode()
    ).hexdigest()
