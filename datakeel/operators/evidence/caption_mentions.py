# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize deterministic caption mentions with NFC Unicode evidence spans."""

import re
import unicodedata
from pathlib import Path

from pydantic import ConfigDict

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.evidence_models import EvidenceValue, ExtractorRef, TextSpan
from datakeel.core.models import BoundaryModel, FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.evidence.common import EvidenceParams, anchor, publish, subject
from datakeel.operators.evidence.contracts import Concept, read_lexicon
from datakeel.operators.evidence.facts import CaptionFacts

VERSION = "1.0"


class CaptionDocument(BoundaryModel):
    """Parse a caption field while allowing unrelated COCO sidecar properties."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    caption: str


def _read_caption(file: FileItem) -> str:
    text = Path(file.path).read_text(encoding="utf-8")
    if Path(file.filename).suffix.lower() == ".json":
        text = CaptionDocument.model_validate_json(text).caption
    return unicodedata.normalize("NFC", text)


def _pattern(concept: Concept) -> str:
    aliases = sorted(concept.synonyms, key=lambda value: (-len(value), value))
    return "|".join(
        rf"(?<!\w){re.escape(alias)}(?!\w)" if alias.isascii() else re.escape(alias)
        for alias in aliases
    )


def _mentions(file: FileItem, params: EvidenceParams) -> FileItem:
    owner, sidecar = subject(file), sample_sidecars(file).caption
    text, failed = None, False
    if sidecar is not None:
        try:
            text = _read_caption(sidecar)
        except (OSError, ValueError):
            failed = True
    drafts: list[ObservationDraft] = []
    concepts: list[str] = []
    for concept in read_lexicon().concepts:
        matches = list(re.finditer(_pattern(concept), text or "", re.IGNORECASE))
        spans = [TextSpan(start=match.start(), end=match.end()) for match in matches]
        if spans:
            concepts.append(concept.id)
        evidence = tuple(anchor(sidecar or file, owner, span) for span in spans)
        if not evidence:
            evidence = (anchor(file if failed else sidecar or file, owner),)
        drafts.append(
            ObservationDraft(
                subject=owner,
                predicate="mentions",
                object=EvidenceValue(concept=concept.id, value="present" if spans else "unknown"),
                anchors=evidence,
                extractor=ExtractorRef(
                    id="evidence.caption_mentions", version=params.extractor_version
                ),
                confidence=1 if spans else None,
                reason="Lexicon match" if spans else "Caption unavailable or concept not observed",
            )
        )
    facts = CaptionFacts(
        caption_text=text, caption_mentions=tuple(concepts), caption_available=text is not None
    )
    return publish(file, drafts, failed=failed, **facts.model_dump(mode="json"))


def execute(files: list[FileItem], _output_dir: Path, params: EvidenceParams) -> OperatorResult:
    """Emit present or unknown mentions, preserving normalized-code-point anchors."""
    return summarize(files, [_mentions(file, params) for file in files])


OPERATOR = Operator("evidence.caption_mentions", "image", "evidence", EvidenceParams, execute)
