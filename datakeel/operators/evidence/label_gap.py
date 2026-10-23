# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare canonical caption and annotation concepts without inventing absence."""

from pathlib import Path

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.evidence_models import EvidenceValue, ExtractorRef
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.evidence.common import EvidenceParams, anchor, publish, subject
from datakeel.operators.evidence.contracts import read_lexicon
from datakeel.operators.evidence.facts import annotation_facts, caption_facts

VERSION = "1.0"


def _gaps(file: FileItem, params: EvidenceParams) -> FileItem:
    owner, sidecars = subject(file), sample_sidecars(file)
    caption, annotation = caption_facts(file), annotation_facts(file)
    drafts: list[ObservationDraft] = []
    concepts = [concept.id for concept in read_lexicon().concepts if concept.kind == "object"]
    for concept in concepts:
        if caption.caption_available and annotation.annotation_available:
            if (
                concept not in caption.caption_mentions
                or concept in annotation.annotation_categories
            ):
                continue
            value = "present"
        else:
            value = "unknown"
        inputs = [file]
        if sidecars.caption is not None and caption.caption_available:
            inputs.append(sidecars.caption)
        if sidecars.annotation is not None and annotation.annotation_available:
            inputs.append(sidecars.annotation)
        drafts.append(
            ObservationDraft(
                subject=owner,
                predicate="label_gap",
                object=EvidenceValue(concept=concept, value=value),
                anchors=tuple(anchor(item, owner) for item in inputs),
                extractor=ExtractorRef(id="evidence.label_gap", version=params.extractor_version),
                confidence=1 if value == "present" else None,
                reason="Mentioned concept missing from supplied annotations"
                if value == "present"
                else "Caption or annotation evidence unavailable",
            )
        )
    return publish(file, drafts)


def execute(files: list[FileItem], _output_dir: Path, params: EvidenceParams) -> OperatorResult:
    """Emit only positive gaps or unknown states when required sidecars are unavailable."""
    return summarize(files, [_gaps(file, params) for file in files])


OPERATOR = Operator("evidence.label_gap", "image", "evidence", EvidenceParams, execute)
