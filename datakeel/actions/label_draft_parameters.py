# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled drafting of an unpublished label set version and its annotation guidelines."""

from typing import Literal

from pydantic import Field, model_validator

from datakeel.core.models import BoundaryModel

DraftProfile = Literal["offline", "cloud-text", "cloud-vision"]


class DraftLabelSetParams(BoundaryModel):
    """Name the sources a draft may read and the model budget a person approves.

    Sources may be combined: data standards (field or code-list codes), existing annotations
    (label sets and annotated datasets) and sampled files. ``offline`` drafts from the
    sources deterministically; the cloud profiles send the listed sources to a model.
    """

    request_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    topic: str = Field(default="", max_length=500)
    language: Literal["zh", "en"] = "zh"
    dataset_id: str | None = None
    version_id: str | None = None
    sample_ids: tuple[str, ...] = Field(default=(), max_length=50)
    standard_codes: tuple[str, ...] = Field(default=(), max_length=50)
    label_set_ids: tuple[str, ...] = Field(default=(), max_length=20)
    annotation_dataset_ids: tuple[str, ...] = Field(default=(), max_length=20)
    profile: DraftProfile = "offline"
    max_cost_usd: float = Field(default=0, ge=0, le=50, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_source(self) -> "DraftLabelSetParams":
        """A draft needs a standard, existing annotations or sample files to start from."""
        if not (
            self.sample_ids
            or self.standard_codes
            or self.label_set_ids
            or self.annotation_dataset_ids
        ):
            message = "Drafting needs a data standard, existing annotations or sample files"
            raise ValueError(message)
        if self.sample_ids and self.dataset_id is None:
            message = "Sample files require their dataset_id"
            raise ValueError(message)
        if self.profile != "offline" and self.max_cost_usd <= 0:
            message = "A model profile requires a positive max_cost_usd budget"
            raise ValueError(message)
        return self


DRAFT_POLICIES: dict[str, tuple[str, bool, str]] = {
    "draft_label_set": (
        "production:manage",
        False,
        "Draft an unpublished label set version and guidelines; model use costs money",
    ),
}
