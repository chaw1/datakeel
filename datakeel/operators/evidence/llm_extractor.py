# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Define an offline scripted adapter boundary without provider or budget integration."""

from typing import Protocol

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import EvidenceValue, ExtractorRef, PredicateId
from datakeel.core.models import BoundaryModel, FileItem
from datakeel.operators.evidence.common import anchor, subject


class ScriptedFact(BoundaryModel):
    """Configure one deterministic fake extraction response."""

    predicate: PredicateId = "mentions"
    object: EvidenceValue


class ExtractorAdapter(Protocol):
    """Allow later model-backed adapters to return the same typed observation boundary."""

    def extract(self, file: FileItem) -> tuple[ObservationDraft, ...]:
        """Produce observations without persisting assertions or dispatching actions."""
        ...


class FakeExtractor:
    """Return a fixed local script without network access, tokens, or traces."""

    def __init__(self, script: tuple[ScriptedFact, ...], version: str = "1.0") -> None:
        """Store immutable scripted observations for repeatable adapter tests."""
        self.script = script
        self.version = version

    def extract(self, file: FileItem) -> tuple[ObservationDraft, ...]:
        """Bind a scripted response to the provided source bytes and identity."""
        owner = subject(file)
        return tuple(
            ObservationDraft(
                subject=owner,
                predicate=fact.predicate,
                object=fact.object,
                anchors=(anchor(file, owner),),
                extractor=ExtractorRef(id="evidence.llm_extractor", version=self.version),
                reason="Scripted offline fixture",
            )
            for fact in self.script
        )
