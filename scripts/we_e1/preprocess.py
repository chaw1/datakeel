# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned fake-only image bytes and exact UTF-8 text preprocessing."""

import base64
import hashlib
from io import BytesIO
from typing import Literal

from PIL import Image, ImageOps
from pydantic import model_validator

from scripts.we_e1.models import Boundary, Digest

MAX_IMAGE_BYTES = 3_000_000
MAX_IMAGE_SIDE = 512
TEXT_LIMIT = 8192
BATCH_LIMIT = 10


class ContractError(ValueError):
    """Expose a stable contract reason without fabricating an embedding."""

    def __init__(self, reason: str) -> None:
        """Retain the typed reason without logging any request content."""
        super().__init__(reason)
        self.reason = reason


class Prepared(Boundary):
    """Bind exact post-preprocessing bytes to their immutable version and digest."""

    version: Literal["text-utf8-v1", "image-exif-rgb-png512-v1"]
    payload_base64: str
    payload_sha256: Digest
    data_uri: str | None = None
    prefix_only: Literal[False] = False
    warning: None = None

    @model_validator(mode="after")
    def bind_payload(self) -> "Prepared":
        """Reject a mismatched local hash, invalid UTF-8 or a changed image Data URI."""
        payload = base64.b64decode(self.payload_base64, validate=True)
        if sha256(payload) != self.payload_sha256:
            reason = "prepared_payload_hash_mismatch"
            raise ContractError(reason)
        if self.version == "text-utf8-v1":
            payload.decode("utf-8")
            if self.data_uri is not None:
                reason = "text_data_uri_forbidden"
                raise ContractError(reason)
        elif self.data_uri != "data:image/png;base64," + self.payload_base64:
            reason = "image_data_uri_mismatch"
            raise ContractError(reason)
        return self


def sha256(data: bytes) -> str:
    """Hash exact bytes using the same algorithm for every development artifact."""
    return hashlib.sha256(data).hexdigest()


def prepare_text(text: str, *, tokenizer: Literal["fake-codepoint-v1"] | None) -> Prepared:
    """Preserve text verbatim; an unknown token bound blocks, with no truncation."""
    if tokenizer is None:
        msg = "token_bound_unknown"
        raise ContractError(msg)
    if not text:
        msg = "empty_input"
        raise ContractError(msg)
    if len(text) > TEXT_LIMIT:
        msg = "too_long_no_automatic_prefix"
        raise ContractError(msg)
    payload = text.encode("utf-8")
    return Prepared(
        version="text-utf8-v1",
        payload_base64=base64.b64encode(payload).decode("ascii"),
        payload_sha256=sha256(payload),
    )


def prepare_image(original: bytes) -> Prepared:
    """Transpose EXIF, remove metadata and encode RGB PNG without center cropping."""
    with Image.open(BytesIO(original)) as source:
        corrected = ImageOps.exif_transpose(source).convert("RGB")
        corrected.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
        clean = Image.frombytes("RGB", corrected.size, corrected.tobytes())
        output = BytesIO()
        clean.save(output, format="PNG", optimize=False, compress_level=9)
    payload = output.getvalue()
    if len(payload) > MAX_IMAGE_BYTES:
        msg = "image_payload_too_large"
        raise ContractError(msg)
    encoded = base64.b64encode(payload).decode("ascii")
    return Prepared(
        version="image-exif-rgb-png512-v1",
        payload_base64=encoded,
        payload_sha256=sha256(payload),
        data_uri="data:image/png;base64," + encoded,
    )
