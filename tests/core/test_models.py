# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate immutable identity, timestamp, and serialization contracts."""

from datetime import UTC
from uuid import UUID

import pytest
from pydantic import ValidationError

from datakeel.core.models import AssetRef, FileItem, JsonDocument, LineageEvent, new_id, utcnow


def test_new_identity_when_called_twice_is_distinct_uuid() -> None:
    """Verify new identity when called twice is distinct uuid."""
    first, second = new_id(), new_id()
    assert first != second
    assert UUID(first).version == UUID(second).version == 4


def test_current_timestamp_when_created_is_aware_utc() -> None:
    """Verify current timestamp when created is aware utc."""
    assert utcnow().tzinfo is UTC


def test_asset_ref_when_unknown_field_present_rejects_input() -> None:
    """Verify asset ref when unknown field present rejects input."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AssetRef.model_validate({"asset_id": "one", "undeclared": True})


def test_asset_ref_when_reassigned_is_immutable() -> None:
    """Verify asset ref when reassigned is immutable."""
    asset = AssetRef(asset_id="one")
    with pytest.raises(ValidationError, match="frozen_instance"):
        asset.asset_id = "two"


def test_record_mapping_when_optional_field_absent_preserves_default() -> None:
    """Verify record mapping when optional field absent preserves default."""
    asset = AssetRef(asset_id="one")
    assert asset.get("missing", "fallback") == "fallback"


def test_record_mapping_when_serialized_matches_model_fields() -> None:
    """Verify record mapping when serialized matches model fields."""
    asset = AssetRef(asset_id="one")
    keys = list(asset.keys())
    assert dict(asset.items()) == {key: asset[key] for key in keys}


def test_file_metadata_when_one_instance_changes_does_not_leak_to_another() -> None:
    """Verify file metadata when one instance changes does not leak to another."""
    first = FileItem(path="one", filename="one.txt")
    second = FileItem(path="two", filename="two.txt")
    first.metadata["note"] = "local"
    assert second.metadata == {}


def test_event_when_round_tripped_preserves_asset_identity_and_utc_time() -> None:
    """Verify event when round tripped preserves asset identity and utc time."""
    event = LineageEvent(
        idempotency_key="event-one",
        operator="import",
        inputs=[AssetRef(asset_id="source")],
        outputs=[AssetRef(asset_id="result")],
    )
    assert LineageEvent.model_validate_json(event.model_dump_json()) == event


def test_json_document_when_dynamic_vocabulary_used_retains_json_values() -> None:
    """Verify json document when dynamic vocabulary used retains json values."""
    value = {"@type": "Dataset", "nested": {"values": [True, None, 3, "text"]}}
    document = JsonDocument.model_validate(value)
    assert document.model_dump(mode="json") == value


def test_json_document_when_read_as_mapping_preserves_keys_and_defaults() -> None:
    """Verify json document when read as mapping preserves keys and defaults."""
    document = JsonDocument({"name": "sample"})
    assert document["name"] == document.get("name")
    assert document.keys() == {"name"}
    assert document.get("missing", "default") == "default"


def test_json_document_when_non_json_value_present_rejects_input() -> None:
    """Verify json document when non json value present rejects input."""
    with pytest.raises(ValidationError, match="invalid-json-value"):
        JsonDocument.model_validate({"bad": object()})
