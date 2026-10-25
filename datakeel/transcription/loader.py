# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate portable transcription profiles and recordings from checkout or wheel."""

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.transcription_models import TranscriptionProfile, TranscriptionRecording


def contracts_path() -> Path:
    """Resolve the same bundled KG tree without depending on another domain package."""
    package = Path(__file__).resolve().parents[1]
    source = package.parent / "contracts" / "kg"
    return source if source.exists() else package / "_contracts" / "kg"


def load_profile(path: Path) -> TranscriptionProfile:
    """Reject invalid YAML without echoing secret-bearing field values."""
    try:
        return TranscriptionProfile.model_validate(yaml.safe_load(path.read_bytes()))
    except (OSError, yaml.YAMLError, ModelValidationError) as error:
        message = f"{path.name}: invalid transcription profile"
        raise ValidationError(message) from error


def get_profile(identity: str = "replay-image-demo") -> TranscriptionProfile:
    """Resolve a packaged transcription identifier without interpreting it as a path."""
    for path in sorted((contracts_path() / "transcription-profiles").glob("*.yaml")):
        profile = load_profile(path)
        if profile.id == identity:
            return profile
    message = f"Unknown transcription profile: {identity}"
    raise NotFoundError(message)


def read_recording(
    profile: TranscriptionProfile,
) -> tuple[str | None, TranscriptionRecording | None]:
    """Hash validated replay bytes for plan fingerprints and durable cache keys."""
    if not profile.recording:
        return None, None
    path = Path(profile.recording)
    path = path if path.is_absolute() else contracts_path() / path
    try:
        content = path.read_bytes()
        recording = TranscriptionRecording.model_validate(yaml.safe_load(content))
    except (OSError, yaml.YAMLError, ModelValidationError) as error:
        message = "Transcription recording could not be read or validated"
        raise ValidationError(message) from error
    return hashlib.sha256(content).hexdigest(), recording
