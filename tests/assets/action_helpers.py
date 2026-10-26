# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate source-bearing plans without external files, models or shared state."""

from datakeel.core.data_asset_models import DataAsset
from datakeel.core.models import AssetRef, BoundaryModel, FileItem, JsonDocument
from datakeel.storage.database import Database, DatasetRow, VersionRow
from tests.assets.entry_helpers import publish


class ActionSource(BoundaryModel):
    """Keep a generated protected resource and the caption never allowed in denied output."""

    dataset_id: str
    file_id: str
    marker: str
    asset: DataAsset


def seed_action_source(db: Database) -> ActionSource:
    """Publish one real dataset policy whose original file and dataset metadata contain data."""
    marker = "Generated protected caption 730251"
    file = FileItem(
        id="source-file",
        path="generated.txt",
        filename="generated.txt",
        size=20,
        sha256="a" * 64,
        modality="text",
        metadata={"caption_text": marker},
    )
    with db.session() as session:
        session.add(
            DatasetRow(
                id="source-dataset",
                name="Generated source",
                files=[file.model_dump()],
                metadata_values={"source_note": marker},
            )
        )
        session.flush()
        session.add(
            VersionRow(
                id="source-version", dataset_id="source-dataset", manifest=[file.model_dump()]
            )
        )
        session.commit()
    asset = publish(db, AssetRef(asset_id="source-dataset"))
    return ActionSource(dataset_id="source-dataset", file_id=file.id, marker=marker, asset=asset)


def source_params(source: ActionSource) -> JsonDocument:
    """Select the generated manifest through the normal action selection contract."""
    return JsonDocument({"selection": {"dataset_id": source.dataset_id}})
