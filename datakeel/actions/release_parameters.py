# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Canonical publication intent for the existing single-use approval boundary."""

from pydantic import Field, field_validator

from datakeel.core.models import BoundaryModel


class DeliveryReviewInput(BoundaryModel):
    """Select the immutable directory split checked for this publication."""

    split_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_version_id: str | None = Field(default=None, min_length=1)


class PublishReleaseParams(BoundaryModel):
    """Freeze one dataset version under a unique semantic release label."""

    dataset_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    tag: str = Field(
        pattern=r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$",
        max_length=100,
    )
    notes: str = Field(default="", max_length=10000)
    delivery_review: DeliveryReviewInput | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @field_validator("tag")
    @classmethod
    def semantic_prerelease(cls, value: str) -> str:
        """Reject leading zeroes in numeric SemVer prerelease identifiers."""
        prerelease = value.split("+", 1)[0].partition("-")[2]
        if any(
            part.isdecimal() and part != "0" and part.startswith("0")
            for part in prerelease.split(".")
        ):
            message = "Numeric release prerelease identifiers cannot have leading zeroes"
            raise ValueError(message)
        return value
