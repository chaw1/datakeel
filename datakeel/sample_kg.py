# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate attributed text fixtures without turning evaluation labels into product observations."""

from pathlib import Path

from pydantic import Field

from datakeel.core.kg_eval_models import KGCaseSuite
from datakeel.core.models import BoundaryModel
from datakeel.kg.loader import contracts_path, load_contract


class KGTextFixture(BoundaryModel):
    """Carry only source text and a filename identity, never expected extraction labels."""

    id: str
    text: str


class ScriptedDocuments(BoundaryModel):
    """Describe the clearly labelled multi-paragraph fake-extractor samples."""

    documents: tuple[KGTextFixture, ...] = Field(min_length=3, max_length=3)


class TruncatedFixture(BoundaryModel):
    """Carry the text matched by the deliberately truncated replay fixture."""

    text: str


class KGSampleFiles(BoundaryModel):
    """Separate real recorded passages from synthetic scripted extraction sources."""

    recorded: tuple[Path, ...]
    scripted: tuple[Path, ...]
    truncated: Path

    @property
    def paths(self) -> tuple[Path, ...]:
        """Return all generated inputs in stable order for dataset import."""
        return (*self.recorded, *self.scripted, self.truncated)


def recorded_documents() -> tuple[KGTextFixture, ...]:
    """Read the 24 exact gold passages while discarding every evaluation annotation."""
    suite = load_contract(contracts_path() / "eval/cases.yaml", KGCaseSuite)
    return tuple(KGTextFixture(id=case.id, text=case.text) for case in suite.cases)


def _write(directory: Path, document: KGTextFixture) -> Path:
    path = directory / f"{document.id}.txt"
    path.write_text(document.text, encoding="utf-8")
    return path


def generate_kg_samples(directory: Path) -> KGSampleFiles:
    """Write recorded passages, three scripted long documents, and one visible failure."""
    directory.mkdir(parents=True, exist_ok=True)
    scripted = load_contract(contracts_path() / "demo/long-documents.yaml", ScriptedDocuments)
    truncated = load_contract(contracts_path() / "eval/truncated.yaml", TruncatedFixture)
    return KGSampleFiles(
        recorded=tuple(_write(directory, item) for item in recorded_documents()),
        scripted=tuple(_write(directory, item) for item in scripted.documents),
        truncated=_write(directory, KGTextFixture(id="scripted-truncated", text=truncated.text)),
    )
