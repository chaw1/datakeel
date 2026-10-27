# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable facts, cited sentences, and versioned dataset documentation."""

from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field, JsonValue

from datakeel.core.models import BoundaryModel, new_id, utcnow

DatasheetLanguage = Literal["zh", "en"]
DatasheetChapter = Literal[
    "motivation",
    "composition",
    "collection",
    "preprocessing",
    "uses",
    "distribution",
    "maintenance",
]
DATASHEET_CHAPTERS: tuple[DatasheetChapter, ...] = (
    "motivation",
    "composition",
    "collection",
    "preprocessing",
    "uses",
    "distribution",
    "maintenance",
)


class DatasheetFact(BoundaryModel):
    """Freeze one deterministic platform value together with its source coordinates."""

    id: str = Field(min_length=1)
    chapter: DatasheetChapter
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    value: JsonValue
    recorded_at: AwareDatetime


class DatasheetSentence(BoundaryModel):
    """Carry proposed text and explicit references before independent verification."""

    text: str = Field(min_length=1, max_length=20000)
    fact_ids: tuple[str, ...] = ()


class DatasheetSection(BoundaryModel):
    """Represent one fixed chapter and disclose when usable facts are absent."""

    key: DatasheetChapter
    title: str = Field(min_length=1)
    sentences: tuple[DatasheetSentence, ...] = ()
    missing: bool = False


class DroppedSentence(BoundaryModel):
    """Preserve rejected text and every independent citation failure reason."""

    text: str
    fact_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = Field(min_length=1)


class DatasheetValidation(BoundaryModel):
    """Return the seven checked chapters and an explicit rejected-sentence ledger."""

    sections: tuple[DatasheetSection, ...]
    dropped_sentences: tuple[DroppedSentence, ...] = ()


class DatasheetDraft(BoundaryModel):
    """Restrict model output to proposed chapter text and cited fact identities."""

    sections: tuple[DatasheetSection, ...]


class DatasheetDocument(BoundaryModel):
    """Bind checked documentation to one immutable dataset version and fact snapshot."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )

    id: str = Field(default_factory=new_id)
    dataset_id: str
    version_id: str
    language: DatasheetLanguage = "zh"
    created_at: AwareDatetime = Field(default_factory=utcnow)
    facts: tuple[DatasheetFact, ...]
    sections: tuple[DatasheetSection, ...]
    dropped_sentences: tuple[DroppedSentence, ...] = ()
    mode: Literal["template", "model"] = "template"
    published: bool = False
    stale: bool = False


class DatasheetFactChange(BoundaryModel):
    """Describe one stable fact identity added, removed, or changed between drafts."""

    fact_id: str
    before: JsonValue = None
    after: JsonValue = None
    kind: Literal["added", "removed", "changed"]


class DatasheetComparison(BoundaryModel):
    """Compare saved documents without re-reading mutable platform state."""

    before_id: str
    after_id: str
    changes: tuple[DatasheetFactChange, ...] = ()
    changed_chapters: tuple[DatasheetChapter, ...] = ()
