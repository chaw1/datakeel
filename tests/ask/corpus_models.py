# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed, independently authored question corpus and evaluation receipts."""

from pathlib import Path
from typing import Literal

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.knowledge_models import KnowledgeIntent
from datakeel.core.link_models import LinkContext
from datakeel.core.models import BoundaryModel

type CorpusSplit = Literal["development", "holdout"]


class CorpusSubject(BoundaryModel):
    """Describe one synthetic identity before constructing any product fixtures."""

    id: str
    name: str
    kind: Literal["metric", "table", "view", "person", "team", "role"]
    split: CorpusSplit
    aliases: tuple[str, ...] = ()

    @property
    def asset_id(self) -> str:
        """Expand table identities into their complete catalog paths."""
        return f"corpus/main/{self.id}" if self.kind in {"table", "view"} else self.id


class CorpusCatalog(BoundaryModel):
    """Keep vocabulary separate from the questions and their ground truth."""

    version: Literal[1]
    subjects: tuple[CorpusSubject, ...]


class CorpusCase(BoundaryModel):
    """Bind a question to a manually selected route, intent and subject."""

    id: str
    question: str
    route: Literal["knowledge", "metric"]
    intent: KnowledgeIntent | None
    subject_id: str
    language: Literal["zh", "en"]
    position: Literal["start", "middle", "end"]
    tag: str


class QuestionCorpus(BoundaryModel):
    """Load one fixed partition without reading the other partition's questions."""

    version: Literal[1]
    split: CorpusSplit
    cases: tuple[CorpusCase, ...]


class CorpusFixture(BoundaryModel):
    """Provide registered metadata and independent document entity identities."""

    catalog: CorpusCatalog
    snapshot: CatalogSnapshot
    graph: LinkContext


class CorpusResult(BoundaryModel):
    """Preserve observable production answers for a single question."""

    case_id: str
    expected_route: Literal["knowledge", "metric"]
    actual_route: Literal["knowledge", "metric"]
    expected_intent: KnowledgeIntent | None
    actual_intent: KnowledgeIntent | None
    expected_subject: str
    actual_subject: str | None
    numeric_result: bool
    correct: bool


class CorpusReport(BoundaryModel):
    """Report route safety independently from joint intent and identity accuracy."""

    split: CorpusSplit
    corpus_sha256: str
    knowledge_total: int
    knowledge_correct: int
    knowledge_numeric: int
    knowledge_metric_routes: int
    metric_total: int
    metric_correct: int
    results: tuple[CorpusResult, ...]


def corpus_path(split: CorpusSplit) -> Path:
    """Locate a fixed corpus relative to this module, independent of working directory."""
    return Path(__file__).with_name(f"knowledge_corpus_{split}.json")


def load_corpus(split: CorpusSplit) -> QuestionCorpus:
    """Read exactly the requested split and validate every ground truth field."""
    return QuestionCorpus.model_validate_json(corpus_path(split).read_text(encoding="utf-8"))
