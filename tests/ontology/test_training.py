# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Discovered training reads share pinned measurements and enforce saved split ownership."""

from pathlib import Path

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.core.training_models import LeakageReport, SplitRequest, SplitSet
from datakeel.harness.training_cases import seed_training_case
from datakeel.mcp.catalog import tool_definitions
from datakeel.ontology.functions import invoke_function
from datakeel.storage.database import Database
from datakeel.storage.training_store import create_split, list_splits


def test_training_tools_preview_and_read_saved_measurements(db: Database, tmp_path: Path) -> None:
    """Defaults resolve the latest immutable version; an explicit saved ID retains its seed."""
    fixture = seed_training_case(db, tmp_path)
    query = JsonDocument({"dataset_id": fixture.dataset_id})
    result = invoke_function(db, "training_distribution", query)
    preview = SplitSet.model_validate(result.data)
    assert preview.version_id == fixture.version_id
    assert not list_splits(db, fixture.dataset_id, fixture.version_id)
    external = invoke_function(db, "training_leakage", query)
    assert len(LeakageReport.model_validate(external.data).pairs) == 2
    split = create_split(
        db, fixture.dataset_id, fixture.version_id, SplitRequest(name="saved", seed=7)
    )
    arguments = JsonDocument({"dataset_id": fixture.dataset_id, "split_set_id": split.id})
    saved = invoke_function(db, "training_distribution", arguments)
    assert SplitSet.model_validate(saved.data) == split
    safe = invoke_function(db, "training_leakage", arguments)
    assert not LeakageReport.model_validate(safe.data).pairs
    assert saved.asset_refs[0].version == fixture.version_id
    names = {item.name for item in tool_definitions()}
    assert {"training_distribution", "training_leakage"} <= names


def test_training_tools_reject_saved_split_version_mismatch(db: Database, tmp_path: Path) -> None:
    """A caller cannot label measurements from one saved version as another source."""
    fixture = seed_training_case(db, tmp_path)
    split = create_split(db, fixture.dataset_id, fixture.version_id, SplitRequest(name="saved"))
    query = JsonDocument(
        {
            "dataset_id": fixture.dataset_id,
            "version_id": "different-version",
            "split_set_id": split.id,
        }
    )
    with pytest.raises(ValidationError, match="requested version"):
        invoke_function(db, "training_distribution", query)
