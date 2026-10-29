# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit, conservative audio synchronization results."""

from typing import Literal

from pydantic import Field, model_validator

from datakeel.core.errors import ValidationError
from datakeel.core.models import Record


class MediaAlignment(Record):
    """Describe a recording's shared signal relative to the first input.

    A positive offset means the shared signal occurs later in this recording;
    subtract the offset from this recording's timestamps to match the reference.
    Unalignable signals have a null offset, never an invented zero offset.
    """

    reference_file_id: str
    offset_ms: float | None = Field(default=None, allow_inf_nan=False)
    confidence: float = Field(default=0.0, ge=0, le=1)
    aligned: bool = False
    reason: Literal[
        "reference", "matched", "silence", "ambiguous", "no_common_signal", "missing_audio"
    ]

    @model_validator(mode="after")
    def consistent_alignment(self) -> "MediaAlignment":
        """Prevent contradictory success states and fabricated failure offsets."""
        if self.aligned != (self.offset_ms is not None):
            msg = "Aligned recordings require an offset; unalignable recordings forbid one"
            raise ValidationError(msg)
        if self.aligned != (self.reason in {"reference", "matched"}):
            msg = "Alignment reason must agree with its success state"
            raise ValidationError(msg)
        if self.reason == "reference" and self.offset_ms != 0:
            msg = "The reference recording must have a zero offset"
            raise ValidationError(msg)
        return self
