# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read the frozen canonical table-owner list independently of contributions."""

from importlib.resources import files

from pydantic import TypeAdapter

from datakeel.core.models import BoundaryModel
from datakeel.core.schema import CanonicalSchema, InstallerRequirement, TableOwner


class _InventoryTable(BoundaryModel):
    table: str
    owner: str
    row_class: str
    source_module: str
    batch: str


def canonical_schema() -> CanonicalSchema:
    """Load the byte copy frozen before implementation, never infer from imports."""
    entries = TypeAdapter(tuple[_InventoryTable, ...]).validate_json(
        files("datakeel.persistence").joinpath("canonical_tables.json").read_bytes()
    )
    vector_entries = TypeAdapter(tuple[_InventoryTable, ...]).validate_json(
        files("datakeel.persistence").joinpath("vector_tables.json").read_bytes()
    )
    return CanonicalSchema(
        tables=tuple(
            TableOwner(table=item.table, owner=item.owner) for item in (*entries, *vector_entries)
        ),
        owners=(
            "action_store",
            "annotation_store",
            "ask_store",
            "asset_store",
            "catalog_store",
            "conversation_store",
            "dataset_store",
            "datasheet_store",
            "delivery_store",
            "evidence_store",
            "harness_store",
            "intent_store",
            "kg_eval_store",
            "kg_store",
            "llm_data_store",
            "memory_store",
            "metric_store",
            "operator_store",
            "production_store",
            "quality_store",
            "runtime_store",
            "training_store",
            "transcription_store",
            "worker_store",
            "workflow_store",
            "vector_store",
        ),
        installers=(
            InstallerRequirement(key="file_discovery", owner="dataset_store", order=0),
            InstallerRequirement(key="evidence", owner="evidence_store", order=1),
            InstallerRequirement(key="release", owner="delivery_store", order=2),
            InstallerRequirement(key="asset", owner="asset_store", order=3),
            InstallerRequirement(key="training", owner="training_store", order=4),
            InstallerRequirement(key="llm_data", owner="llm_data_store", order=5),
            InstallerRequirement(key="production", owner="production_store", order=6),
            InstallerRequirement(key="lineage", owner="dataset_store", order=7),
        ),
    )
