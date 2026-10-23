# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable question identity and NFC content revisions without ask-service imports."""

import hashlib
import unicodedata
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from datakeel.core.models import AssetRef, BoundaryModel


def question_revision(text: str) -> str:
    """Hash the exact NFC-normalized question text addressed by Unicode spans."""
    return hashlib.sha256(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()


class QuestionProperties(BoundaryModel):
    """Bind a question to its answer identity, session, and immutable text content."""

    id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    content_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_instant: AwareDatetime

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        """Require normalized content and its independently reproducible digest."""
        if self.text != unicodedata.normalize("NFC", self.text):
            msg = "Question text must use NFC normalization"
            raise ValueError(msg)
        if self.content_revision != question_revision(self.text):
            msg = "Question content revision must match its normalized text"
            raise ValueError(msg)
        return self

    def asset_ref(self) -> AssetRef:
        """Use the answer id for both stable question identity and immutable version."""
        return AssetRef(asset_type="question", asset_id=self.id, version=self.id)
