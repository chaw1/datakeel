# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Small generated manifests and documentation snapshots for storage tests."""

from datakeel.core.datasheet_models import DatasheetDocument
from datakeel.core.models import FileItem
from datakeel.datasheets.templates import build_template
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.datasheet_facts import extract_facts


def dataset_versions(db: Database) -> tuple[str, str, str]:
    """Create two distinguishable immutable versions and a contradictory current file list."""
    before = FileItem(
        id="original-file",
        path="unmaterialized",
        filename="original.txt",
        modality="text",
        size=10,
        sha256="a" * 64,
    )
    after = FileItem(
        id="new-file",
        path="unmaterialized",
        filename="new.png",
        modality="image",
        size=20,
        sha256="b" * 64,
    )
    with db.session() as session:
        dataset = DatasetRow(
            name="Generated datasheet",
            files=[],
            created_at=100,
            metadata_values={
                "description": "Generated observations",
                "creator": "Fixture creator",
                "license": "CC0-1.0",
            },
        )
        session.add(dataset)
        session.flush()
        first = VersionRow(
            dataset_id=dataset.id, created_at=200, manifest=[before.model_dump(mode="json")]
        )
        second = VersionRow(
            dataset_id=dataset.id,
            created_at=300,
            manifest=[before.model_dump(mode="json"), after.model_dump(mode="json")],
        )
        session.add_all((first, second))
        session.commit()
        return dataset.id, first.id, second.id


def saved_draft(db: Database, dataset_id: str, version_id: str) -> DatasheetDocument:
    """Build a deterministic draft from exactly the requested manifest version."""
    with db.session() as session:
        facts = extract_facts(session, dataset_id, version_id)
    validation = build_template(facts)
    return DatasheetDocument(
        dataset_id=dataset_id, version_id=version_id, facts=facts, sections=validation.sections
    )
