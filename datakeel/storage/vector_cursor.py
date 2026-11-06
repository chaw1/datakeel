# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Short-lived, process-local signed cursors; restart requires fresh pagination."""

import base64
import binascii
import hashlib
import hmac
import secrets

from pydantic import Field
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel, utcnow
from datakeel.core.vector_models import Digest

_SIGNING_KEY = secrets.token_bytes(32)
CURSOR_SECONDS = 1800


class VectorCursor(BoundaryModel):
    """Authenticate the complete query snapshot, actor, database and page offset."""

    binding: Digest
    offset: int = Field(gt=0)
    expires: int


def encode_cursor(binding: str, offset: int) -> str:
    """Sign an opaque continuation that cannot be moved across queries or users."""
    payload = (
        VectorCursor(
            binding=binding, offset=offset, expires=int(utcnow().timestamp()) + CURSOR_SECONDS
        )
        .model_dump_json()
        .encode()
    )
    signature = hmac.digest(_SIGNING_KEY, payload, hashlib.sha256)
    return base64.urlsafe_b64encode(signature + payload).decode()


def cursor_offset(token: str | None, binding: str, total: int) -> int:
    """Reject forgery, expiry and changed snapshots rather than mixing result pages."""
    if token is None:
        return 0
    try:
        cursor = _decode(token)
    except (ValueError, binascii.Error, ModelValidationError) as error:
        msg = "vector_cursor_invalid_or_stale: restart pagination"
        raise ValidationError(msg) from error
    if (
        cursor.binding != binding
        or cursor.expires <= int(utcnow().timestamp())
        or cursor.offset >= total
    ):
        msg = "vector_cursor_invalid_or_stale: restart pagination"
        raise ValidationError(msg)
    return cursor.offset


def _decode(token: str) -> VectorCursor:
    raw = base64.b64decode(token, altchars=b"-_", validate=True)
    signature, payload = raw[:32], raw[32:]
    if not hmac.compare_digest(signature, hmac.digest(_SIGNING_KEY, payload, hashlib.sha256)):
        raise ValueError
    return VectorCursor.model_validate_json(payload)
