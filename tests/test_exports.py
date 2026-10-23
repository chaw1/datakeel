# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for exports."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from datakeel.core.models import AssetRef, FileItem, LineageEvent
from datakeel.lineage.exports import export_croissant, export_openlineage

FIXTURES = Path(__file__).parent / "fixtures"


def test_official_openlineage_schema_is_pinned_and_unmodified() -> None:
    """Verify official openlineage schema is pinned and unmodified."""
    provenance = json.loads((FIXTURES / "openlineage-provenance.json").read_text())
    assert (
        hashlib.sha256((FIXTURES / "openlineage-2-0-2.json").read_bytes()).hexdigest()
        == provenance["sha256"]
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("COMPLETED", "COMPLETE"),
        ("FAILED", "FAIL"),
        ("RUNNING", "RUNNING"),
        ("CANCELLED", "ABORT"),
        ("QUEUED", "OTHER"),
    ],
)
def test_export_validates_against_official_schema_offline(state: str, expected: str) -> None:
    """Verify export validates against official schema offline."""
    event = LineageEvent(
        event_id="not-assumed-to-be-a-uuid",
        idempotency_key="run:1",
        operator="image.resize",
        inputs=[AssetRef(asset_id="data", version="1")],
        outputs=[AssetRef(asset_id="data", version="2")],
        params={"width": 100},
        quality={"total": 90},
        run_state=state,
        occurred_at=datetime(2026, 10, 22, 12),  # noqa: DTZ001 - verify naive legacy records.
    )
    exported = export_openlineage([event])[0]
    schema = json.loads((FIXTURES / "openlineage-2-0-2.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(exported.root)
    assert exported["eventType"] == expected
    assert exported["run"]["runId"] == export_openlineage([event])[0]["run"]["runId"]
    assert exported["outputs"][0]["outputFacets"]["datakeel_quality"]["metrics"] == {"total": 90}
    assert exported["outputs"][0]["facets"]["datakeel_asset"]["version"] == "2"


def test_croissant_11_required_fields_and_resolvable_record_sources() -> None:
    """Verify croissant 11 required fields and resolvable record sources."""
    files = [
        FileItem(
            id="a",
            path="objects/hash-a",
            filename="image.png",
            modality="image",
            size=10,
            sha256="a" * 64,
        ),
        FileItem(
            id="b",
            path="objects/hash-b",
            filename="document.txt",
            modality="text",
            size=12,
            sha256="b" * 64,
        ),
    ]
    document = export_croissant(
        {
            "id": "demo",
            "name": "Demo",
            "base_url": "https://example.test",
            "created_at": "2026-10-22T12:00:00Z",
            "metadata": {
                "description": "Generated examples",
                "creator": "Datakeel example generator",
                "license": "https://spdx.org/licenses/Apache-2.0.html",
            },
        },
        files,
    )
    assert document["conformsTo"] == "http://mlcommons.org/croissant/1.1"
    assert document["@type"] == "sc:Dataset"
    assert {
        "@context",
        "description",
        "name",
        "license",
        "url",
        "creator",
        "datePublished",
        "distribution",
        "recordSet",
    } <= document.keys()
    assert document["@context"]["conformsTo"] == "dct:conformsTo"
    resources = {item["@id"]: item for item in document["distribution"]}
    assert len(resources) == len(files)
    for record in document["recordSet"]:
        field = record["field"][0]
        source = resources[field["source"]["fileObject"]["@id"]]
        assert source["sha256"]
        assert source["contentUrl"].startswith("https://example.test/api/datasets/demo/files/")
        assert field["source"]["extract"]["fileProperty"] == "content"
    assert "objects/hash" not in json.dumps(document.root)
    assert document["recordSet"][0]["field"][0]["dataType"] == "sc:ImageObject"
    assert document["recordSet"][1]["field"][0]["dataType"] == "sc:Text"


def test_unspecified_license_does_not_claim_reuse_permissions() -> None:
    """Verify unspecified license does not claim reuse permissions."""
    document = export_croissant({"id": "a", "name": "Example"}, [])
    assert document["license"]["@type"] == "CreativeWork"
    assert "no reuse permission" in document["license"]["name"]
    assert document["distribution"] == []
    assert document["recordSet"] == []


def test_croissant_converts_database_epoch_to_valid_publication_timestamp() -> None:
    """Verify croissant converts database epoch to valid publication timestamp."""
    document = export_croissant({"id": "demo", "created_at": 1792670400.0}, [])
    publication = datetime.fromisoformat(document["datePublished"])
    assert publication.tzinfo is not None
    assert publication.timestamp() == 1792670400.0
