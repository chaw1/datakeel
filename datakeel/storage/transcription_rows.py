# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist complete transcription snapshots for reuse across authorized graph runs."""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class TranscriptionRow(Base):
    """Store text, corrected OCR coordinates and provenance under the full input digest."""

    __tablename__ = "image_transcripts"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
