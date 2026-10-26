# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Canonical hashing and JSON Schema validation for delivery contracts."""

import hashlib
import json
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator, validate
from pydantic import JsonValue

from datakeel.core.delivery_models import DeliveryManifest
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument


def canonical_hash(document: dict[str, JsonValue]) -> str:
    """Hash all manifest fields except the self-referential checksum."""
    payload = {key: value for key, value in document.items() if key != "manifest_sha256"}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def manifest_hash(manifest: DeliveryManifest) -> str:
    """Compute the documented canonical checksum of a typed manifest."""
    return canonical_hash(manifest.model_dump(mode="json"))


def validate_manifest(manifest: DeliveryManifest) -> None:
    """Validate an export against the same JSON Schema shipped in contracts/."""
    package = Path(__file__).resolve().parents[1]
    source = package.parent / "contracts" / "delivery-manifest.schema.json"
    path = source if source.is_file() else package / "_contracts" / source.name
    schema = JsonDocument.model_validate_json(path.read_bytes()).root
    validate(manifest.model_dump(mode="json"), schema, cls=Draft202012Validator)
    paths = [item.path for item in manifest.files]
    if len(paths) != len(set(paths)):
        message = "Duplicate delivery payload paths"
        raise ValidationError(message)
    for path in paths:
        safe_relative(path)
    if manifest.manifest_sha256 != manifest_hash(manifest):
        message = "Manifest checksum mismatch"
        raise ValidationError(message)


def safe_relative(value: str) -> PurePosixPath:
    """Reject aliases, traversal, drive paths and ambiguous archive members."""
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or ":" in value
        or str(path) != value
        or value in {"MANIFEST.json", "RECORDS.json"}
    ):
        message = "Unsafe delivery payload path"
        raise ValidationError(message)
    return path


def file_hash(path: Path) -> str:
    """Stream a SHA-256 checksum without loading the object into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
