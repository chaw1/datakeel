# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""E1-compatible preprocessing and final fake request serialization; no transport."""

import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError, __version__

from datakeel.core.models import BoundaryModel, FileItem
from datakeel.core.vector_models import EmbedParams, FrozenPayload, VectorError, vector_hash

TEXT_LIMIT = 8192
IMAGE_DIMENSIONS = 1024
MAX_IMAGE_BYTES = 3000000


class PreparedWire(BoundaryModel):
    """Hold bytes only in memory; persistent plans and audits retain hashes."""

    frozen: FrozenPayload
    body: bytes


def _image(original: bytes) -> bytes:
    with Image.open(BytesIO(original)) as source:
        corrected = ImageOps.exif_transpose(source).convert("RGB")
        corrected.thumbnail((512, 512), Image.Resampling.LANCZOS)
        clean = Image.frombytes("RGB", corrected.size, corrected.tobytes())
        output = BytesIO()
        clean.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _content(original: bytes, params: EmbedParams) -> tuple[bytes, str | None]:
    if params.modality == "text":
        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError:
            return b"", "invalid_utf8"
        if not text:
            return b"", "empty_input"
        if len(text) > TEXT_LIMIT:
            return b"", "too_long_no_automatic_prefix"
        return original, None
    if params.dimensions != IMAGE_DIMENSIONS:
        msg = "image_dimension_must_be_1024"
        raise VectorError(msg)
    try:
        image = _image(original)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError):
        return b"", "invalid_image"
    return (b"", "image_payload_too_large") if len(image) > MAX_IMAGE_BYTES else (image, None)


def prepare_wire(file: FileItem, params: EmbedParams) -> PreparedWire:
    """Recompute original, final per-item and serialized request identities locally."""
    original = Path(file.path).read_bytes()
    revision = hashlib.sha256(original).hexdigest()
    if revision != file.sha256 or file.modality != params.modality:
        msg = "frozen_content_or_modality_changed"
        raise VectorError(msg)
    payload, failure = _content(original, params)
    preprocessing = (
        "text-utf8-v1"
        if params.modality == "text"
        else f"image-exif-rgb-png512-v1:pillow-{__version__}"
    )
    token_bound = (
        (len(payload.decode("utf-8")) if params.modality == "text" else params.policy.image_tokens)
        if not failure
        else 0
    )
    body = _body(payload, params) if not failure else b""
    payload_hash = hashlib.sha256(payload).hexdigest() if not failure else None
    body_hash = hashlib.sha256(body).hexdigest() if not failure else None
    # Deliberately excludes asset identity, manifest version, peers and run identity.
    key = vector_hash(
        {
            "content_revision": revision,
            "payload": payload_hash,
            "body": body_hash,
            "preprocessing": preprocessing,
            "params": params.model_dump(mode="json", exclude={"policy"}),
            "failure": failure,
        }
    )
    return PreparedWire(
        frozen=FrozenPayload(
            asset_id=file.id,
            content_revision=revision,
            payload_hash=payload_hash,
            body_hash=body_hash,
            preprocessing=preprocessing,
            token_bound=token_bound,
            failure=failure,
            cache_key=key,
        ),
        body=body,
    )


def _body(payload: bytes, params: EmbedParams) -> bytes:
    request = (
        {
            "model": "text-embedding-v4",
            "input": [payload.decode("utf-8")],
            "dimensions": params.dimensions,
            "encoding_format": "float",
        }
        if params.modality == "text"
        else {
            "model": "multimodal-embedding-v1",
            "input": [{"image": "data:image/png;base64," + base64.b64encode(payload).decode()}],
        }
    )
    return json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
